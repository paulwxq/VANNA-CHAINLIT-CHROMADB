"""
Data Pipeline 独立日志管理器

专门为data_pipeline模块设计的日志管理器，完全独立于主项目的日志系统
"""

import os
from pathlib import Path
from typing import Dict

# 明确导入Python内置logging模块
import logging as std_logging


class DataPipelineLogManager:
    """Data Pipeline 专用日志管理器"""
    
    _loggers: Dict[str, std_logging.Logger] = {}
    _file_handlers: Dict[str, std_logging.FileHandler] = {}
    
    @classmethod
    def get_logger(cls, name: str, task_id: str) -> std_logging.Logger:
        """
        获取或创建logger
        
        Args:
            name: logger名称
            task_id: 任务ID，用于确定日志文件位置
        
        Returns:
            配置好的logger实例
        """
        logger_key = f"data_pipeline.{name}.{task_id}"
        
        if logger_key not in cls._loggers:
            logger = cls._create_logger(name, task_id)
            cls._loggers[logger_key] = logger
        
        return cls._loggers[logger_key]
    
    @classmethod
    def _create_logger(cls, name: str, task_id: str) -> std_logging.Logger:
        """创建新的logger实例"""
        # 创建logger
        logger_name = f"data_pipeline.{name}"
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
        file_handler = cls._create_file_handler(task_id)
        if file_handler:
            logger.addHandler(file_handler)
        
        return logger
    
    @classmethod
    def _create_console_handler(cls) -> std_logging.StreamHandler:
        """创建控制台处理器"""
        handler = std_logging.StreamHandler()
        handler.setLevel(std_logging.INFO)
        
        formatter = std_logging.Formatter(
            '%(asctime)s [%(levelname)s] Pipeline: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        return handler
    
    @classmethod
    def _create_file_handler(cls, task_id: str) -> std_logging.FileHandler:
        """创建文件处理器"""
        try:
            # 获取项目根目录的绝对路径
            project_root = Path(__file__).parent.parent.parent
            task_dir = project_root / "data_pipeline" / "training_data" / task_id
            
            task_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = task_dir / "data_pipeline.log"
            
            # 为每个任务创建独立的文件处理器
            handler_key = f"file_handler_{task_id}"
            
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
            sys.stderr.write(f"[WARNING] 无法创建data_pipeline日志文件处理器: {e}\n")
            return None
    
    @classmethod
    def cleanup_logger(cls, task_id: str):
        """清理指定任务的logger和文件处理器"""
        try:
            # 关闭文件处理器
            handler_key = f"file_handler_{task_id}"
            if handler_key in cls._file_handlers:
                cls._file_handlers[handler_key].close()
                del cls._file_handlers[handler_key]
            
            # 清理相关的logger
            keys_to_remove = [key for key in cls._loggers.keys() if task_id in key]
            for key in keys_to_remove:
                logger = cls._loggers[key]
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()
                del cls._loggers[key]
                
        except Exception as e:
            import sys
            sys.stderr.write(f"[WARNING] 清理data_pipeline日志资源失败: {e}\n")
    
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
            sys.stderr.write(f"[WARNING] 清理所有data_pipeline日志资源失败: {e}\n")