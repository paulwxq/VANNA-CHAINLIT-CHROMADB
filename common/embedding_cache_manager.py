import redis
import json
import hashlib
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
import app_config
from core.logging import get_app_logger


class EmbeddingCacheManager:
    """Embedding向量缓存管理器"""
    
    def __init__(self):
        """初始化缓存管理器"""
        self.logger = get_app_logger("EmbeddingCacheManager")
        self.redis_client = None
        self.cache_enabled = app_config.ENABLE_EMBEDDING_CACHE
        
        if self.cache_enabled:
            try:
                self.redis_client = redis.Redis(
                    host=app_config.REDIS_HOST,
                    port=app_config.REDIS_PORT,
                    db=app_config.REDIS_DB,
                    password=app_config.REDIS_PASSWORD,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # 测试连接
                self.redis_client.ping()
                self.logger.debug("Embedding缓存管理器初始化成功")
            except Exception as e:
                self.logger.warning(f"Redis连接失败，embedding缓存将被禁用: {e}")
                self.cache_enabled = False
                self.redis_client = None
    
    def is_available(self) -> bool:
        """检查缓存是否可用"""
        return self.cache_enabled and self.redis_client is not None
    
    def _get_cache_key(self, question: str, model_info: Dict[str, str]) -> str:
        """
        生成缓存键
        
        Args:
            question: 问题文本
            model_info: 模型信息字典，包含model_name和embedding_dimension
            
        Returns:
            缓存键字符串
        """
        # 使用问题的hash值避免键太长
        question_hash = hashlib.sha256(question.encode('utf-8')).hexdigest()[:16]
        model_name = model_info.get('model_name', 'unknown')
        dimension = model_info.get('embedding_dimension', 'unknown')
        
        return f"embedding_cache:{question_hash}:{model_name}:{dimension}"
    
    def _get_model_info(self) -> Dict[str, str]:
        """
        获取当前模型信息
        
        Returns:
            包含model_name和embedding_dimension的字典
        """
        try:
            from common.utils import get_current_embedding_config
            embedding_config = get_current_embedding_config()
            
            return {
                'model_name': embedding_config.get('model_name', 'unknown'),
                'embedding_dimension': str(embedding_config.get('embedding_dimension', 'unknown'))
            }
        except Exception as e:
            self.logger.warning(f"获取模型信息失败: {e}")
            return {'model_name': 'unknown', 'embedding_dimension': 'unknown'}
    
    def get_cached_embedding(self, question: str) -> Optional[List[float]]:
        """
        从缓存中获取embedding向量
        
        Args:
            question: 问题文本
            
        Returns:
            如果缓存命中返回向量列表，否则返回None
        """
        if not self.is_available():
            return None
        
        try:
            model_info = self._get_model_info()
            cache_key = self._get_cache_key(question, model_info)
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                data = json.loads(cached_data)
                vector = data.get('vector')
                if vector:
                    self.logger.debug(f"✓ Embedding缓存命中: {question[:50]}...")
                    return vector
            
            return None
            
        except Exception as e:
            self.logger.warning(f"获取embedding缓存失败: {e}")
            return None
    
    def cache_embedding(self, question: str, vector: List[float]) -> bool:
        """
        将embedding向量保存到缓存
        
        Args:
            question: 问题文本
            vector: embedding向量
            
        Returns:
            成功返回True，失败返回False
        """
        if not self.is_available() or not vector:
            return False
        
        try:
            model_info = self._get_model_info()
            cache_key = self._get_cache_key(question, model_info)
            
            cache_data = {
                "question": question,
                "vector": vector,
                "model_name": model_info['model_name'],
                "dimension": len(vector),
                "created_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            # 设置缓存，使用配置的TTL
            ttl = app_config.EMBEDDING_CACHE_TTL
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data, ensure_ascii=False)
            )
            
            self.logger.debug(f"✓ Embedding向量已缓存: {question[:50]}... (维度: {len(vector)})")
            
            # 检查缓存大小并清理
            self._cleanup_if_needed()
            
            return True
            
        except Exception as e:
            self.logger.warning(f"缓存embedding失败: {e}")
            return False
    
    def _cleanup_if_needed(self):
        """
        如果缓存大小超过限制，清理最旧的缓存
        """
        try:
            max_size = app_config.EMBEDDING_CACHE_MAX_SIZE
            pattern = "embedding_cache:*"
            
            # 获取所有embedding缓存键
            keys = self.redis_client.keys(pattern)
            
            if len(keys) > max_size:
                # 需要清理，获取键的TTL信息并按剩余时间排序
                keys_with_ttl = []
                for key in keys:
                    ttl = self.redis_client.ttl(key)
                    if ttl > 0:  # 只考虑有TTL的键
                        keys_with_ttl.append((key, ttl))
                
                # 按TTL升序排序（剩余时间少的在前面）
                keys_with_ttl.sort(key=lambda x: x[1])
                
                # 删除超出限制的旧键
                cleanup_count = len(keys) - max_size
                keys_to_delete = [key for key, _ in keys_with_ttl[:cleanup_count]]
                
                if keys_to_delete:
                    self.redis_client.delete(*keys_to_delete)
                    self.logger.debug(f"清理了 {len(keys_to_delete)} 个旧的embedding缓存")
                    
        except Exception as e:
            self.logger.warning(f"清理embedding缓存失败: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计信息的字典
        """
        stats = {
            "enabled": self.cache_enabled,
            "available": self.is_available(),
            "total_count": 0,
            "memory_usage_mb": 0
        }
        
        if not self.is_available():
            return stats
        
        try:
            pattern = "embedding_cache:*"
            keys = self.redis_client.keys(pattern)
            stats["total_count"] = len(keys)
            
            # 估算内存使用量（粗略计算）
            if keys:
                sample_key = keys[0]
                sample_data = self.redis_client.get(sample_key)
                if sample_data:
                    avg_size_bytes = len(sample_data.encode('utf-8'))
                    total_size_bytes = avg_size_bytes * len(keys)
                    stats["memory_usage_mb"] = round(total_size_bytes / (1024 * 1024), 2)
            
        except Exception as e:
            self.logger.warning(f"获取缓存统计失败: {e}")
        
        return stats
    
    def clear_all_cache(self) -> bool:
        """
        清空所有embedding缓存
        
        Returns:
            成功返回True，失败返回False
        """
        if not self.is_available():
            return False
        
        try:
            pattern = "embedding_cache:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                self.redis_client.delete(*keys)
                self.logger.debug(f"已清空所有embedding缓存 ({len(keys)} 条)")
                return True
            else:
                self.logger.debug("没有embedding缓存需要清空")
                return True
                
        except Exception as e:
            self.logger.warning(f"清空embedding缓存失败: {e}")
            return False


# 全局实例
_embedding_cache_manager = None

def get_embedding_cache_manager() -> EmbeddingCacheManager:
    """
    获取全局embedding缓存管理器实例
    
    Returns:
        EmbeddingCacheManager实例
    """
    global _embedding_cache_manager
    if _embedding_cache_manager is None:
        _embedding_cache_manager = EmbeddingCacheManager()
    return _embedding_cache_manager 