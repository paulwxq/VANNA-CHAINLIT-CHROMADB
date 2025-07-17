"""
Data Pipeline 统一日志管理
支持API和命令行两种模式
"""

from core.logging import get_data_pipeline_logger, initialize_logging
import os
import logging
import logging.handlers
from pathlib import Path

def init_data_pipeline_logging():
    """初始化data_pipeline日志系统"""
    # 确保日志系统已初始化
    initialize_logging()

def get_logger(name: str, task_id: str = None):
    """
    获取data_pipeline专用logger
    
    Args:
        name: logger名称
        task_id: 任务ID（可选，用于任务特定日志）
    
    Returns:
        配置好的logger实例
    """
    logger = get_data_pipeline_logger(name)
    
    # 如果提供了task_id，添加任务特定的文件处理器
    if task_id:
        # 创建任务特定的日志文件
        task_log_file = Path(f"data_pipeline/training_data/{task_id}/data_pipeline.log")
        task_log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建任务特定的文件处理器（支持滚动）
        task_handler = logging.handlers.RotatingFileHandler(
            task_log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        task_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        task_handler.setFormatter(formatter)
        
        # 添加到logger
        logger.addHandler(task_handler)
    
    return logger