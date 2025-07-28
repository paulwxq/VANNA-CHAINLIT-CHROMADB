# agent/config.py
"""
Agent配置文件
定义所有Agent相关的配置参数，便于调优

配置说明：
- 所有阈值参数都支持运行时调整，无需重启应用
- 置信度参数范围通常在 0.0-1.0 之间
- 迭代次数参数影响性能和准确性的平衡
"""

AGENT_CONFIG = {
    # ==================== 问题分类器配置 ====================
    "classification": {
        # 高置信度阈值：当规则分类的置信度 >= 此值时，直接使用规则分类结果，不再调用LLM
        # 建议范围：0.7-0.9，过高可能错过需要LLM辅助的边界情况，过低会增加LLM调用成本
        "high_confidence_threshold": 0.7,
        
        # 低置信度阈值：当规则分类的置信度 <= 此值时，启用LLM二次分类进行辅助判断
        # 建议范围：0.2-0.5，过高会频繁调用LLM，过低可能错过需要LLM辅助的情况
        "low_confidence_threshold": 0.4,
        
        # 最大置信度上限：规则分类计算出的置信度不会超过此值，防止过度自信
        # 建议范围：0.8-1.0，通常设为0.9以保留不确定性空间
        "max_confidence": 0.9,
        
        # 基础置信度：规则分类的起始置信度，会根据匹配的关键词数量递增
        # 建议范围：0.3-0.6，这是匹配到1个关键词时的基础置信度
        "base_confidence": 0.4,
        
        # 置信度增量步长：每匹配一个额外关键词，置信度增加的数值
        # 建议范围：0.05-0.2，过大会导致置信度增长过快，过小则区分度不够
        "confidence_increment": 0.08,
        
        # LLM分类失败时的默认置信度：当LLM调用异常或解析失败时使用
        # 建议范围：0.3-0.6，通常设为中等水平，避免过高或过低的错误影响
        "llm_fallback_confidence": 0.5,
        
        # 不确定分类的默认置信度：当规则分类无法明确判断时使用
        # 建议范围：0.1-0.3，应设为较低值，表示确实不确定
        "uncertain_confidence": 0.2,
    },
    
    # ==================== 数据库Agent配置 ====================
    "database_agent": {
        # Agent最大迭代次数：防止无限循环，每次迭代包含一轮工具调用
        # 建议范围：3-10，过少可能无法完成复杂查询，过多会影响响应时间
        # 典型流程：1.生成SQL → 2.执行SQL → 3.生成摘要 = 3次迭代
        "max_iterations": 5,
        
        # 是否启用详细日志：True时会输出Agent的详细执行过程，便于调试
        # 生产环境建议设为False以减少日志量，开发环境建议设为True
        "enable_verbose": True,
        
        # 早停策略：当Agent认为任务完成时的停止方法
        # 可选值："generate"(生成完成即停止) | "force"(强制完成所有步骤)
        # "generate"更高效，"force"更稳定但可能产生冗余步骤
        "early_stopping_method": "generate",
    },
    
    # ==================== 聊天Agent配置 ====================
    "chat_agent": {
        # 聊天Agent最大迭代次数：聊天场景通常比数据库查询简单，迭代次数可以更少
        # 建议范围：1-5，通常1-2次就能完成聊天响应
        "max_iterations": 3,
        
        # 是否启用详细日志：同数据库Agent，控制日志详细程度
        "enable_verbose": True,
        
        # 是否注入分类上下文信息：True时会将分类原因作为上下文传递给聊天Agent
        # 帮助聊天Agent更好地理解用户意图，但会增加prompt长度
        "enable_context_injection": True,
    },
    
    # ==================== 健康检查配置 ====================
    "health_check": {
        # 健康检查使用的测试问题：用于验证系统基本功能是否正常
        # 建议使用简单的问候语，避免复杂查询影响检查速度
        "test_question": "你好",
        
        # 是否启用完整流程测试：True时会执行完整的问题处理流程
        # False时只检查基本组件状态，True时更全面但耗时更长
        "enable_full_test": True,
    },
    
    # ==================== 性能优化配置 ====================
    "performance": {
        # 是否启用Agent实例重用：True时会预创建Agent实例并重复使用
        # 优点：减少初始化时间，提高响应速度
        # 缺点：占用更多内存，可能存在状态污染风险
        # 生产环境建议启用，内存受限环境可关闭
        "enable_agent_reuse": True,
    },
    
    # ==================== SQL验证配置 ====================
    "sql_validation": {
        # 是否启用禁止词检查：检查SQL中是否包含危险操作
        # 禁止词检查优先级高于语法检查，失败时不尝试修复
        "enable_forbidden_check": True,
        
        # 是否启用语法验证：使用EXPLAIN SQL验证语法正确性
        # 语法验证失败时可以尝试LLM修复
        "enable_syntax_validation": True,
        
        # 是否启用自动修复：当语法验证失败时，调用LLM尝试修复
        # 仅对语法错误有效，禁止词错误不会尝试修复
        "enable_auto_repair": True,
        
        # 禁止的SQL操作：这些操作会被直接拒绝，不允许执行
        # 系统只支持查询操作，不允许修改数据
        "forbidden_operations": ['UPDATE', 'DELETE', 'DROP', 'ALTER', 'INSERT'],
        
        # LLM修复超时时间：单次修复调用的最大等待时间（秒）
        # 超时后将放弃修复，直接返回失败
        "repair_timeout": 60,
        
        # 修复重试次数：目前固定为1次，不进行多次重试
        # 这是设计约束，避免无限修复循环
        "max_repair_attempts": 1,
    },
}

def get_nested_config(config: dict, key_path: str, default=None):
    """
    获取嵌套配置值
    
    Args:
        config: 配置字典
        key_path: 嵌套键路径，如 "classification.high_confidence_threshold"
        default: 默认值，当配置项不存在时返回
        
    Returns:
        配置值或默认值
        
    Example:
        >>> config = {"classification": {"high_confidence_threshold": 0.8}}
        >>> get_nested_config(config, "classification.high_confidence_threshold", 0.5)
        0.8
        >>> get_nested_config(config, "classification.missing_key", 0.5)
        0.5
    """
    keys = key_path.split('.')
    current = config
    
    try:
        for key in keys:
            current = current[key]
        return current
    except (KeyError, TypeError):
        return default

def get_current_config() -> dict:
    """
    获取当前配置
    
    Returns:
        完整的Agent配置字典
        
    Note:
        此函数返回的是配置的引用，修改返回值会影响全局配置
        如需修改配置，建议创建副本后再修改
    """
    return AGENT_CONFIG

# ==================== 分类器词典配置加载 ====================

try:
    from .dict_loader import load_classifier_dict_config, get_dict_loader
    
    def get_classifier_dict_config(force_reload: bool = False):
        """
        获取分类器词典配置
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            ClassifierDictConfig: 词典配置对象
        """
        return load_classifier_dict_config(force_reload)
    
    def reload_classifier_dict_config():
        """重新加载分类器词典配置"""
        return load_classifier_dict_config(force_reload=True)
    
    # 导出词典配置函数
    __all__ = [
        'get_current_config', 
        'get_nested_config', 
        'AGENT_CONFIG',
        'get_classifier_dict_config',
        'reload_classifier_dict_config'
    ]
    
except ImportError as e:
    # 如果dict_loader模块不存在，提供空实现
    def get_classifier_dict_config(force_reload: bool = False):
        raise ImportError("词典加载器模块不可用，请检查dict_loader.py是否存在")
    
    def reload_classifier_dict_config():
        raise ImportError("词典加载器模块不可用，请检查dict_loader.py是否存在") 