import redis
import json
import hashlib
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from app_config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD,
    CONVERSATION_CONTEXT_COUNT, CONVERSATION_MAX_LENGTH, USER_MAX_CONVERSATIONS,
    CONVERSATION_TTL, USER_CONVERSATIONS_TTL, QUESTION_ANSWER_TTL,
    ENABLE_CONVERSATION_CONTEXT, ENABLE_QUESTION_ANSWER_CACHE,
    DEFAULT_ANONYMOUS_USER
)

class RedisConversationManager:
    """Redis对话管理器 - 修正版"""
    
    def __init__(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            self.redis_client.ping()
            print(f"[REDIS_CONV] Redis连接成功: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            print(f"[ERROR] Redis连接失败: {str(e)}")
            self.redis_client = None
    
    def is_available(self) -> bool:
        """检查Redis是否可用"""
        try:
            return self.redis_client is not None and self.redis_client.ping()
        except:
            return False
    
    # ==================== 用户ID解析（修正版）====================
    
    def resolve_user_id(self, user_id_from_request: Optional[str], 
                       session_id: Optional[str], request_ip: str,
                       login_user_id: Optional[str] = None) -> str:
        """
        智能解析用户ID - 统一版
        
        Args:
            user_id_from_request: 请求参数中的user_id
            session_id: 浏览器session_id  
            request_ip: 请求IP地址
            login_user_id: 从Flask session中获取的登录用户ID
        """
        
        # 1. 优先使用登录用户ID
        if login_user_id:
            print(f"[REDIS_CONV] 使用登录用户ID: {login_user_id}")
            return login_user_id
        
        # 2. 如果没有登录，尝试从请求参数获取user_id
        if user_id_from_request:
            print(f"[REDIS_CONV] 使用请求参数user_id: {user_id_from_request}")
            return user_id_from_request
        
        # 3. 都没有则为匿名用户（统一为guest）
        print(f"[REDIS_CONV] 使用匿名用户: {DEFAULT_ANONYMOUS_USER}")
        return DEFAULT_ANONYMOUS_USER
    
    def resolve_conversation_id(self, user_id: str, conversation_id_input: Optional[str], 
                              continue_conversation: bool) -> tuple[str, dict]:
        """
        智能解析对话ID - 改进版
        
        Returns:
            tuple: (conversation_id, status_info)
            status_info包含:
            - status: "existing" | "new" | "invalid_id_new"
            - message: 状态说明
            - requested_id: 原始请求的ID（如果有）
        """
        
        # 1. 如果指定了conversation_id，验证后使用
        if conversation_id_input:
            if self._is_valid_conversation(conversation_id_input, user_id):
                print(f"[REDIS_CONV] 使用指定对话: {conversation_id_input}")
                return conversation_id_input, {
                    "status": "existing",
                    "message": "继续已有对话"
                }
            else:
                print(f"[WARN] 无效的conversation_id: {conversation_id_input}，创建新对话")
                new_conversation_id = self.create_conversation(user_id)
                return new_conversation_id, {
                    "status": "invalid_id_new",
                    "message": "您请求的对话不存在或无权访问，已为您创建新对话",
                    "requested_id": conversation_id_input
                }
        
        # 2. 如果要继续最近对话
        if continue_conversation:
            recent_conversation = self._get_recent_conversation(user_id)
            if recent_conversation:
                print(f"[REDIS_CONV] 继续最近对话: {recent_conversation}")
                return recent_conversation, {
                    "status": "existing",
                    "message": "继续最近对话"
                }
        
        # 3. 创建新对话
        new_conversation_id = self.create_conversation(user_id)
        print(f"[REDIS_CONV] 创建新对话: {new_conversation_id}")
        return new_conversation_id, {
            "status": "new",
            "message": "创建新对话"
        }
    
    def _is_valid_conversation(self, conversation_id: str, user_id: str) -> bool:
        """验证对话是否存在且属于该用户"""
        if not self.is_available():
            return False
        
        try:
            # 检查对话元信息是否存在
            meta_data = self.redis_client.hgetall(f"conversation:{conversation_id}:meta")
            if not meta_data:
                return False
            
            # 检查是否属于该用户
            return meta_data.get('user_id') == user_id
            
        except Exception:
            return False
    
    def _get_recent_conversation(self, user_id: str) -> Optional[str]:
        """获取用户最近的对话ID"""
        if not self.is_available():
            return None
        
        try:
            conversations = self.redis_client.lrange(
                f"user:{user_id}:conversations", 0, 0
            )
            return conversations[0] if conversations else None
        except Exception:
            return None
    
    # ==================== 对话管理 ====================
    
    def create_conversation(self, user_id: str) -> str:
        """创建新对话"""
        # 生成包含时间戳的conversation_id
        timestamp = int(datetime.now().timestamp())
        conversation_id = f"conv_{timestamp}_{uuid.uuid4().hex[:8]}"
        
        if not self.is_available():
            return conversation_id  # Redis不可用时返回ID，但不存储
        
        try:
            # 创建对话元信息
            meta_data = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "message_count": "0"
            }
            
            # 保存对话元信息
            self.redis_client.hset(
                f"conversation:{conversation_id}:meta",
                mapping=meta_data
            )
            self.redis_client.expire(f"conversation:{conversation_id}:meta", CONVERSATION_TTL)
            
            # 添加到用户的对话列表
            self._add_conversation_to_user(user_id, conversation_id)
            
            print(f"[REDIS_CONV] 创建对话成功: {conversation_id}")
            return conversation_id
            
        except Exception as e:
            print(f"[ERROR] 创建对话失败: {str(e)}")
            return conversation_id  # 返回ID但可能未存储
    
    def save_message(self, conversation_id: str, role: str, content: str, 
                    metadata: Optional[Dict] = None) -> bool:
        """保存消息到对话历史"""
        if not self.is_available() or not conversation_id:
            return False
        
        try:
            message_data = {
                "message_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "role": role,  # user, assistant
                "content": content,
                "metadata": metadata or {}
            }
            
            # 保存到消息列表（LPUSH添加到头部，最新消息在前）
            self.redis_client.lpush(
                f"conversation:{conversation_id}:messages",
                json.dumps(message_data)
            )
            
            # 设置TTL
            self.redis_client.expire(f"conversation:{conversation_id}:messages", CONVERSATION_TTL)
            
            # 限制消息数量
            self.redis_client.ltrim(
                f"conversation:{conversation_id}:messages",
                0, CONVERSATION_MAX_LENGTH - 1
            )
            
            # 更新元信息
            self._update_conversation_meta(conversation_id)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 保存消息失败: {str(e)}")
            return False
    
    def get_context(self, conversation_id: str, count: Optional[int] = None) -> str:
        """获取对话上下文，格式化为prompt"""
        if not self.is_available() or not ENABLE_CONVERSATION_CONTEXT:
            return ""
        
        try:
            if count is None:
                count = CONVERSATION_CONTEXT_COUNT
            
            # 获取最近的消息（count*2 因为包含用户和助手消息）
            message_count = count * 2
            messages = self.redis_client.lrange(
                f"conversation:{conversation_id}:messages",
                0, message_count - 1
            )
            
            if not messages:
                return ""
            
            # 解析消息并构建上下文（按时间正序）
            context_parts = []
            for msg_json in reversed(messages):  # Redis返回倒序，需要反转
                try:
                    msg_data = json.loads(msg_json)
                    role = msg_data.get("role", "")
                    content = msg_data.get("content", "")
                    
                    if role == "user":
                        context_parts.append(f"User: {content}")
                    elif role == "assistant":
                        context_parts.append(f"Assistant: {content}")
                        
                except json.JSONDecodeError:
                    continue
            
            context = "\n".join(context_parts)
            print(f"[REDIS_CONV] 获取上下文成功: {len(context_parts)}条消息")
            return context
            
        except Exception as e:
            print(f"[ERROR] 获取上下文失败: {str(e)}")
            return ""
    
    def get_conversation_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict]:
        """获取对话的消息列表"""
        if not self.is_available():
            return []
        
        try:
            if limit:
                messages = self.redis_client.lrange(
                    f"conversation:{conversation_id}:messages", 0, limit - 1
                )
            else:
                messages = self.redis_client.lrange(
                    f"conversation:{conversation_id}:messages", 0, -1
                )
            
            # 解析并按时间正序返回
            parsed_messages = []
            for msg_json in reversed(messages):  # 反转为时间正序
                try:
                    parsed_messages.append(json.loads(msg_json))
                except json.JSONDecodeError:
                    continue
                    
            return parsed_messages
            
        except Exception as e:
            print(f"[ERROR] 获取对话消息失败: {str(e)}")
            return []
    
    def get_conversation_meta(self, conversation_id: str) -> Dict:
        """获取对话元信息"""
        if not self.is_available():
            return {}
        
        try:
            meta_data = self.redis_client.hgetall(f"conversation:{conversation_id}:meta")
            return meta_data if meta_data else {}
        except Exception as e:
            print(f"[ERROR] 获取对话元信息失败: {str(e)}")
            return {}
    
    def get_conversations(self, user_id: str, limit: int = None) -> List[Dict]:
        """获取用户的对话列表（按时间倒序）"""
        if not self.is_available():
            return []
        
        if limit is None:
            limit = USER_MAX_CONVERSATIONS
        
        try:
            # 获取对话ID列表（已经按时间倒序）
            conversation_ids = self.redis_client.lrange(
                f"user:{user_id}:conversations", 0, limit - 1
            )
            
            conversations = []
            for conv_id in conversation_ids:
                meta_data = self.get_conversation_meta(conv_id)
                if meta_data:  # 只返回仍然存在的对话
                    conversations.append(meta_data)
            
            return conversations
            
        except Exception as e:
            print(f"[ERROR] 获取用户对话列表失败: {str(e)}")
            return []
    
    # ==================== 智能缓存（修正版）====================
    
    def get_cached_answer(self, question: str, context: str = "") -> Optional[Dict]:
        """检查问答缓存 - 放宽使用条件，无论是否有上下文都可以查找缓存"""
        if not self.is_available() or not ENABLE_QUESTION_ANSWER_CACHE:
            return None
        
        # 移除上下文检查，允许任何情况下查找缓存
        try:
            cache_key = self._get_cache_key(question)
            cached_answer = self.redis_client.get(cache_key)
            
            if cached_answer:
                context_info = "有上下文" if context else "无上下文"
                print(f"[REDIS_CONV] 缓存命中: {cache_key} ({context_info})")
                return json.loads(cached_answer)
            
            return None
            
        except Exception as e:
            print(f"[ERROR] 获取缓存答案失败: {str(e)}")
            return None
    
    def cache_answer(self, question: str, answer: Dict, context: str = ""):
        """缓存问答结果 - 只缓存无上下文的问答"""
        if not self.is_available() or not ENABLE_QUESTION_ANSWER_CACHE:
            return
        
        # 新增：如果有上下文，不缓存
        if context:
            print(f"[REDIS_CONV] 跳过缓存存储：存在上下文")
            return
        
        try:
            cache_key = self._get_cache_key(question)
            
            # 添加缓存时间戳
            answer_with_meta = {
                **answer,
                "cached_at": datetime.now().isoformat(),
                "original_question": question
            }
            
            # 使用独立key，每个缓存项单独设置TTL
            self.redis_client.setex(
                cache_key, 
                QUESTION_ANSWER_TTL,
                json.dumps(answer_with_meta)
            )
            
            print(f"[REDIS_CONV] 缓存答案成功: {cache_key}")
            
        except Exception as e:
            print(f"[ERROR] 缓存答案失败: {str(e)}")
    
    def _get_cache_key(self, question: str) -> str:
        """生成缓存键 - 简化版，只基于问题本身"""
        normalized = question.strip().lower()
        question_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]
        return f"qa_cache:{question_hash}"
    
    # ==================== 私有方法 ====================
    
    def _add_conversation_to_user(self, user_id: str, conversation_id: str):
        """添加对话到用户列表，按时间自动排序"""
        try:
            # LPUSH添加到列表头部（最新的）
            self.redis_client.lpush(f"user:{user_id}:conversations", conversation_id)
            
            # 统一限制数量
            self.redis_client.ltrim(
                f"user:{user_id}:conversations", 
                0, USER_MAX_CONVERSATIONS - 1
            )
            
            # 统一设置TTL
            self.redis_client.expire(
                f"user:{user_id}:conversations", 
                USER_CONVERSATIONS_TTL
            )
            
        except Exception as e:
            print(f"[ERROR] 添加对话到用户列表失败: {str(e)}")
    
    def _update_conversation_meta(self, conversation_id: str):
        """更新对话元信息"""
        try:
            # 获取消息数量
            message_count = self.redis_client.llen(f"conversation:{conversation_id}:messages")
            
            # 更新元信息
            self.redis_client.hset(
                f"conversation:{conversation_id}:meta",
                mapping={
                    "updated_at": datetime.now().isoformat(),
                    "message_count": str(message_count)
                }
            )
            
        except Exception as e:
            print(f"[ERROR] 更新对话元信息失败: {str(e)}")
    
    # ==================== 管理方法 ====================
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        if not self.is_available():
            return {"available": False}
        
        try:
            # 获取Redis原始内存信息
            redis_info = self.redis_client.info()
            used_memory_bytes = redis_info.get("used_memory", 0)
            
            stats = {
                "available": True,
                "total_users": len(self.redis_client.keys("user:*:conversations")),
                "total_conversations": len(self.redis_client.keys("conversation:*:meta")),
                "cached_qa_count": len(self.redis_client.keys("qa_cache:*")),  # 修正缓存统计
                "redis_info": {
                    "memory_usage_mb": round(used_memory_bytes / (1024 * 1024), 2),  # 统一使用MB格式
                    "connected_clients": redis_info.get("connected_clients")
                }
            }
            
            return stats
            
        except Exception as e:
            print(f"[ERROR] 获取统计信息失败: {str(e)}")
            return {"available": False, "error": str(e)}
    
    def cleanup_expired_conversations(self):
        """清理过期对话（Redis TTL自动处理，这里可添加额外逻辑）"""
        if not self.is_available():
            return
        
        try:
            # 清理用户对话列表中的无效对话ID
            user_keys = self.redis_client.keys("user:*:conversations")
            cleaned_count = 0
            
            for user_key in user_keys:
                conversation_ids = self.redis_client.lrange(user_key, 0, -1)
                valid_ids = []
                
                for conv_id in conversation_ids:
                    # 检查对话是否仍然存在
                    if self.redis_client.exists(f"conversation:{conv_id}:meta"):
                        valid_ids.append(conv_id)
                    else:
                        cleaned_count += 1
                
                # 如果有无效ID，重建列表
                if len(valid_ids) != len(conversation_ids):
                    self.redis_client.delete(user_key)
                    if valid_ids:
                        self.redis_client.lpush(user_key, *reversed(valid_ids))
                        # 重新设置TTL
                        self.redis_client.expire(user_key, USER_CONVERSATIONS_TTL)
            
            print(f"[REDIS_CONV] 清理完成，移除了 {cleaned_count} 个无效对话引用")
            
        except Exception as e:
            print(f"[ERROR] 清理失败: {str(e)}")
    
    # ==================== 问答缓存管理方法 ====================
    
    def get_qa_cache_stats(self) -> Dict:
        """获取问答缓存详细统计信息"""
        if not self.is_available():
            return {"available": False}
        
        try:
            pattern = "qa_cache:*"
            keys = self.redis_client.keys(pattern)
            
            stats = {
                "available": True,
                "enabled": ENABLE_QUESTION_ANSWER_CACHE,
                "total_count": len(keys),
                "memory_usage_mb": 0,
                "ttl_seconds": QUESTION_ANSWER_TTL,
                "ttl_hours": QUESTION_ANSWER_TTL / 3600
            }
            
            # 估算内存使用量
            if keys:
                sample_key = keys[0]
                sample_data = self.redis_client.get(sample_key)
                if sample_data:
                    avg_size_bytes = len(sample_data.encode('utf-8'))
                    total_size_bytes = avg_size_bytes * len(keys)
                    stats["memory_usage_mb"] = round(total_size_bytes / (1024 * 1024), 2)
            
            return stats
            
        except Exception as e:
            print(f"[ERROR] 获取问答缓存统计失败: {str(e)}")
            return {"available": False, "error": str(e)}
    
    def get_qa_cache_list(self, limit: int = 50) -> List[Dict]:
        """获取问答缓存列表（支持分页）"""
        if not self.is_available() or not ENABLE_QUESTION_ANSWER_CACHE:
            return []
        
        try:
            pattern = "qa_cache:*"
            keys = self.redis_client.keys(pattern)
            
            # 限制返回数量
            if limit > 0:
                keys = keys[:limit]
            
            cache_list = []
            for key in keys:
                try:
                    cached_data = self.redis_client.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        
                        # 获取TTL信息
                        ttl = self.redis_client.ttl(key)
                        
                        cache_item = {
                            "cache_key": key,
                            "question": data.get("original_question", "未知问题"),
                            "cached_at": data.get("cached_at", "未知时间"),
                            "ttl_seconds": ttl,
                            "response_type": data.get("data", {}).get("type", "未知类型"),
                            "has_sql": bool(data.get("data", {}).get("sql")),
                            "has_summary": bool(data.get("data", {}).get("summary"))
                        }
                        
                        cache_list.append(cache_item)
                        
                except json.JSONDecodeError:
                    # 跳过无效的JSON数据
                    continue
                except Exception as e:
                    print(f"[WARNING] 处理缓存项 {key} 失败: {e}")
                    continue
            
            # 按缓存时间倒序排列
            cache_list.sort(key=lambda x: x.get("cached_at", ""), reverse=True)
            
            return cache_list
            
        except Exception as e:
            print(f"[ERROR] 获取问答缓存列表失败: {str(e)}")
            return []
    
    def clear_all_qa_cache(self) -> int:
        """清空所有问答缓存，返回删除的数量"""
        if not self.is_available():
            return 0
        
        try:
            pattern = "qa_cache:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted_count = self.redis_client.delete(*keys)
                print(f"[REDIS_CONV] 清空问答缓存成功，删除了 {deleted_count} 个缓存项")
                return deleted_count
            else:
                print(f"[REDIS_CONV] 没有找到问答缓存项")
                return 0
                
        except Exception as e:
            print(f"[ERROR] 清空问答缓存失败: {str(e)}")
            return 0 