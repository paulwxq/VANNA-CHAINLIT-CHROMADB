# 在 agent/state.py 中更新 AgentState 定义

from typing import TypedDict, Literal, Optional, List, Dict, Any

class AgentState(TypedDict):
    """LangGraph Agent状态定义"""
    
    # 输入信息
    question: str
    session_id: Optional[str]
    
    # 上下文信息
    context_type: Optional[str]  # 上下文类型 ("DATABASE" 或 "CHAT")
    
    # 分类结果
    question_type: Literal["DATABASE", "CHAT", "UNCERTAIN"]
    classification_confidence: float
    classification_reason: str
    classification_method: str  # "rule_based_*", "enhanced_llm", "direct_database", "direct_chat", etc.
    
    # 数据库查询流程状态
    sql: Optional[str]
    sql_generation_attempts: int
    query_result: Optional[Dict[str, Any]]
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
    
    # 路由模式相关
    routing_mode: Optional[str]  # 记录使用的路由模式