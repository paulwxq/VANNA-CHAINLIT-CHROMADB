# agent/tools/__init__.py
"""
Agent工具包 - 使用@tool装饰器定义的工具集合
"""

# 导入所有工具
from .sql_generation import generate_sql
from .sql_execution import execute_sql
from .summary_generation import generate_summary
from .general_chat import general_chat

# 导出工具列表
TOOLS = [
    generate_sql,
    execute_sql, 
    generate_summary,
    general_chat
]

# 导出单个工具（方便按需导入）
__all__ = [
    'TOOLS',
    'generate_sql',
    'execute_sql',
    'generate_summary', 
    'general_chat'
]