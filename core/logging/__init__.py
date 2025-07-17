from .log_manager import LogManager
import logging

# 全局日志管理器实例
_log_manager = LogManager()

def initialize_logging(config_path: str = "config/logging_config.yaml"):
    """初始化项目日志系统"""
    _log_manager.initialize(config_path)

def get_logger(name: str, module: str = "default") -> logging.Logger:
    """获取logger实例 - 主要API"""
    return _log_manager.get_logger(name, module)

# 便捷方法
def get_data_pipeline_logger(name: str) -> logging.Logger:
    """获取data_pipeline模块logger"""
    return get_logger(name, "data_pipeline")

def get_agent_logger(name: str) -> logging.Logger:
    """获取agent模块logger"""
    return get_logger(name, "agent")

def get_vanna_logger(name: str) -> logging.Logger:
    """获取vanna模块logger"""
    return get_logger(name, "vanna")

def get_app_logger(name: str) -> logging.Logger:
    """获取app模块logger"""
    return get_logger(name, "app")

def get_react_agent_logger(name: str) -> logging.Logger:
    """获取react_agent模块logger"""
    return get_logger(name, "react_agent")

# 上下文管理便捷方法
def set_log_context(**kwargs):
    """设置日志上下文（可选）
    示例: set_log_context(user_id='user123', session_id='sess456')
    """
    _log_manager.set_context(**kwargs)

def clear_log_context():
    """清除日志上下文"""
    _log_manager.clear_context() 