# agent/dict_loader.py
"""
分类器词典配置加载器
负责从YAML文件加载分类器词典配置，并提供数据转换和验证功能
"""

import yaml
import os
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from core.logging import get_agent_logger

# 初始化日志 [[memory:3840221]]
logger = get_agent_logger("DictLoader")

@dataclass
class ClassifierDictConfig:
    """分类器词典配置数据类"""
    strong_business_keywords: Dict[str, List[str]]
    query_intent_keywords: List[str]
    non_business_keywords: List[str]
    sql_patterns: List[str]
    chat_keywords: List[str]
    weights: Dict[str, float]
    metadata: Dict[str, Any]

class DictLoader:
    """分类器词典配置加载器"""
    
    def __init__(self, dict_file: str = None):
        """
        初始化加载器
        
        Args:
            dict_file: 词典配置文件路径，默认为agent/classifier_dict.yaml
        """
        if dict_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dict_file = os.path.join(current_dir, "classifier_dict.yaml")
        
        self.dict_file = dict_file
        self.config_cache = None
    
    def load_config(self, force_reload: bool = False) -> ClassifierDictConfig:
        """
        加载词典配置
        
        Args:
            force_reload: 是否强制重新加载，默认使用缓存
            
        Returns:
            ClassifierDictConfig: 词典配置对象
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if self.config_cache is not None and not force_reload:
            return self.config_cache
        
        try:
            logger.info(f"加载词典配置文件: {self.dict_file}")
            
            with open(self.dict_file, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
            
            # 验证配置文件
            self._validate_config(yaml_data)
            
            # 转换数据格式
            config = self._convert_config(yaml_data)
            
            # 缓存配置
            self.config_cache = config
            
            logger.info("词典配置加载成功")
            return config
            
        except FileNotFoundError:
            error_msg = f"词典配置文件不存在: {self.dict_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        except yaml.YAMLError as e:
            error_msg = f"词典配置文件YAML格式错误: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"词典配置加载失败: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _validate_config(self, yaml_data: Dict[str, Any]) -> None:
        """验证配置文件格式和必要字段"""
        required_sections = [
            'strong_business_keywords',
            'query_intent_keywords', 
            'non_business_keywords',
            'sql_patterns',
            'chat_keywords',
            'weights'
        ]
        
        for section in required_sections:
            if section not in yaml_data:
                raise ValueError(f"配置文件缺少必要部分: {section}")
        
        # 验证权重配置
        required_weights = [
            'business_entity',
            'system_indicator', 
            'query_intent',
            'sql_pattern',
            'chat_keyword',
            'non_business_confidence'
        ]
        
        for weight in required_weights:
            if weight not in yaml_data['weights']:
                raise ValueError(f"权重配置缺少: {weight}")
        
        logger.debug("配置文件验证通过")
    
    def _convert_config(self, yaml_data: Dict[str, Any]) -> ClassifierDictConfig:
        """将YAML数据转换为ClassifierDictConfig对象"""
        
        # 转换强业务关键词（保持字典结构）
        strong_business_keywords = {}
        for category, data in yaml_data['strong_business_keywords'].items():
            if isinstance(data, dict) and 'keywords' in data:
                strong_business_keywords[category] = data['keywords']
            else:
                # 兼容简单格式
                strong_business_keywords[category] = data
        
        # 转换查询意图关键词
        query_intent_data = yaml_data['query_intent_keywords']
        if isinstance(query_intent_data, dict) and 'keywords' in query_intent_data:
            query_intent_keywords = query_intent_data['keywords']
        else:
            query_intent_keywords = query_intent_data
        
        # 转换非业务实体词（展平为列表）
        non_business_keywords = self._flatten_non_business_keywords(
            yaml_data['non_business_keywords']
        )
        
        # 转换SQL模式
        sql_patterns = []
        patterns_data = yaml_data['sql_patterns']
        if isinstance(patterns_data, dict) and 'patterns' in patterns_data:
            for pattern_info in patterns_data['patterns']:
                if isinstance(pattern_info, dict):
                    sql_patterns.append(pattern_info['pattern'])
                else:
                    sql_patterns.append(pattern_info)
        else:
            sql_patterns = patterns_data
        
        # 转换其他关键词列表
        chat_keywords = self._extract_keywords_list(yaml_data['chat_keywords'])
        
        return ClassifierDictConfig(
            strong_business_keywords=strong_business_keywords,
            query_intent_keywords=query_intent_keywords,
            non_business_keywords=non_business_keywords,
            sql_patterns=sql_patterns,
            chat_keywords=chat_keywords,
            weights=yaml_data['weights'],
            metadata=yaml_data.get('metadata', {})
        )
    
    def _flatten_non_business_keywords(self, non_business_data: Dict[str, Any]) -> List[str]:
        """将分类的非业务词展平为列表"""
        flattened = []
        
        # 跳过description字段
        for category, keywords in non_business_data.items():
            if category == 'description':
                continue
            if isinstance(keywords, list):
                flattened.extend(keywords)
        
        return flattened
    
    def _extract_keywords_list(self, data: Any) -> List[str]:
        """从可能包含description的数据中提取关键词列表"""
        if isinstance(data, dict) and 'keywords' in data:
            return data['keywords']
        elif isinstance(data, list):
            return data
        else:
            return []

# 全局加载器实例
_dict_loader = None

def get_dict_loader() -> DictLoader:
    """获取全局词典加载器实例"""
    global _dict_loader
    if _dict_loader is None:
        _dict_loader = DictLoader()
    return _dict_loader

def load_classifier_dict_config(force_reload: bool = False) -> ClassifierDictConfig:
    """
    加载分类器词典配置（便捷函数）
    
    Args:
        force_reload: 是否强制重新加载
        
    Returns:
        ClassifierDictConfig: 词典配置对象
    """
    loader = get_dict_loader()
    return loader.load_config(force_reload) 