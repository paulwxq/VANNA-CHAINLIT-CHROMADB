from .log_manager import LogManager
import logging
import platform
import os

# 全局日志管理器实例
_log_manager = LogManager()

def get_platform_specific_config_path() -> str:
    """根据操作系统自动选择合适的日志配置文件"""
    if platform.system() == "Windows":
        config_path = "config/logging_config_windows.yaml"
    else:
        config_path = "config/logging_config.yaml"
    
    # 检查配置文件是否存在，如果不存在则回退到默认配置
    if not os.path.exists(config_path):
        fallback_path = "config/logging_config.yaml"
        if os.path.exists(fallback_path):
            return fallback_path
        else:
            raise FileNotFoundError(f"日志配置文件不存在: {config_path} 和 {fallback_path}")
    
    return config_path

def initialize_logging(config_path: str = None):
    """初始化项目日志系统
    
    Args:
        config_path: 可选的配置文件路径。如果不提供，将根据操作系统自动选择
    """
    if config_path is None:
        config_path = get_platform_specific_config_path()
    
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