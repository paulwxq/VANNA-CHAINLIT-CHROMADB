"""
React Agent 独立日志管理器

专门为 react_agent 模块设计的日志管理器，完全独立于主项目的日志系统
"""

import os
import logging as std_logging
from pathlib import Path
from typing import Dict
from datetime import datetime


class ReactAgentLogManager:
    """React Agent 专用日志管理器"""
    
    _loggers: Dict[str, std_logging.Logger] = {}
    _file_handlers: Dict[str, std_logging.FileHandler] = {}
    
    @classmethod
    def get_logger(cls, name: str) -> std_logging.Logger:
        """
        获取或创建logger
        
        Args:
            name: logger名称
        
        Returns:
            配置好的logger实例
        """
        logger_key = f"react_agent.{name}"
        
        if logger_key not in cls._loggers:
            logger = cls._create_logger(name)
            cls._loggers[logger_key] = logger
        
        return cls._loggers[logger_key]
    
    @classmethod
    def _create_logger(cls, name: str) -> std_logging.Logger:
        """创建新的logger实例"""
        # 创建logger
        logger_name = f"react_agent.{name}"
        logger = std_logging.getLogger(logger_name)
        
        # 设置日志级别
        logger.setLevel(std_logging.DEBUG)
        
        # 防止日志重复（清除已有处理器）
        logger.handlers.clear()
        logger.propagate = False
        
        # 添加控制台处理器
        console_handler = cls._create_console_handler()
        logger.addHandler(console_handler)
        
        # 添加文件处理器
        file_handler = cls._create_file_handler()
        if file_handler:
            logger.addHandler(file_handler)
        
        return logger
    
    @classmethod
    def _create_console_handler(cls) -> std_logging.StreamHandler:
        """创建控制台处理器"""
        handler = std_logging.StreamHandler()
        handler.setLevel(std_logging.INFO)
        
        formatter = std_logging.Formatter(
            '%(asctime)s [%(levelname)s] ReactAgent: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        return handler
    
    @classmethod
    def _create_file_handler(cls) -> std_logging.FileHandler:
        """创建文件处理器"""
        try:
            # 获取项目根目录的绝对路径
            project_root = Path(__file__).parent.parent
            logs_dir = project_root / "logs"
            
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # 使用当前日期作为日志文件名
            today = datetime.now().strftime('%Y%m%d')
            log_file = logs_dir / f"react_agent_{today}.log"
            
            # 为当天创建独立的文件处理器
            handler_key = f"file_handler_{today}"
            
            if handler_key not in cls._file_handlers:
                handler = std_logging.FileHandler(log_file, encoding='utf-8')
                handler.setLevel(std_logging.DEBUG)
                
                formatter = std_logging.Formatter(
                    '%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                handler.setFormatter(formatter)
                
                cls._file_handlers[handler_key] = handler
            
            return cls._file_handlers[handler_key]
            
        except Exception as e:
            # 如果文件处理器创建失败，记录到stderr但不影响程序运行
            import sys
            sys.stderr.write(f"[WARNING] 无法创建react_agent日志文件处理器: {e}\n")
            return None
    
    @classmethod
    def cleanup_today_logger(cls):
        """清理今天的logger和文件处理器"""
        try:
            today = datetime.now().strftime('%Y%m%d')
            handler_key = f"file_handler_{today}"
            
            # 关闭文件处理器
            if handler_key in cls._file_handlers:
                cls._file_handlers[handler_key].close()
                del cls._file_handlers[handler_key]
            
            # 清理相关的logger
            keys_to_remove = [key for key in cls._loggers.keys() if key.startswith("react_agent.")]
            for key in keys_to_remove:
                logger = cls._loggers[key]
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()
                del cls._loggers[key]
                
        except Exception as e:
            import sys
            sys.stderr.write(f"[WARNING] 清理react_agent日志资源失败: {e}\n")
    
    @classmethod
    def cleanup_all(cls):
        """清理所有logger和文件处理器"""
        try:
            # 关闭所有文件处理器
            for handler in cls._file_handlers.values():
                handler.close()
            cls._file_handlers.clear()
            
            # 清理所有logger
            for logger in cls._loggers.values():
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()
            cls._loggers.clear()
            
        except Exception as e:
            import sys
            sys.stderr.write(f"[WARNING] 清理所有react_agent日志资源失败: {e}\n")


def get_react_agent_logger(name: str) -> std_logging.Logger:
    """
    便捷函数：获取react_agent模块的logger
    
    Args:
        name: logger名称
    
    Returns:
        配置好的logger实例
    """
    return ReactAgentLogManager.get_logger(name) 