# agent/state.py
from typing import TypedDict, Literal, Optional, List, Dict, Any

class AgentState(TypedDict):
    """LangGraph Agent状态定义"""
    
    # 输入信息
    question: str
    session_id: Optional[str]
    
    # 分类结果
    question_type: Literal["DATABASE", "CHAT", "UNCERTAIN"]
    classification_confidence: float
    classification_reason: str
    classification_method: str  # "rule", "llm", "hybrid"
    
    # 数据库查询流程状态
    sql: Optional[str]
    sql_generation_attempts: int
    data_result: Optional[Dict[str, Any]]
    summary: Optional[str]
    
    # 聊天响应
    chat_response: Optional[str]
    
    # 最终输出
    final_response: Dict[str, Any]
    
    # 错误处理
    error: Optional[str]
    error_code: Optional[int]
    
    # 流程控制
    current_step: str
    execution_path: List[str]
    retry_count: int
    max_retries: int
    
    # 调试信息
    debug_info: Dict[str, Any]