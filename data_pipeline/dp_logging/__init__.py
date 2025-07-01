"""
Data Pipeline 独立日志管理系统

完全脱离主项目的日志管理，专门为data_pipeline模块设计
支持任务级别的日志文件管理，同时支持API调用和脚本调用
"""

from .manager import DataPipelineLogManager

# 对外接口
def get_logger(name: str, task_id: str):
    """
    获取data_pipeline专用logger
    
    Args:
        name: logger名称 (如: "SchemaWorkflowOrchestrator", "DDLGenerator")
        task_id: 任务ID，必须提供
                API模式: task_YYYYMMDD_HHMMSS
                脚本模式: manual_YYYYMMDD_HHMMSS
    
    Returns:
        配置好的logger，输出到 ./data_pipeline/training_data/{task_id}/data_pipeline.log
    """
    return DataPipelineLogManager.get_logger(name, task_id)

# 便捷方法（保持接口一致性）
def get_data_pipeline_logger(name: str, task_id: str):
    """便捷方法，与get_logger功能相同"""
    return get_logger(name, task_id)