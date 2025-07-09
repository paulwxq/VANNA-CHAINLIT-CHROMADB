"""
定义 StateGraph 的状态
"""
from typing import TypedDict, Annotated, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    StateGraph 中流转的状态对象定义。

    Attributes:
        messages: 对话消息列表，使用 add_messages 聚合。
        user_id: 当前用户ID。
        thread_id: 当前会话的线程ID。
        suggested_next_step: 用于引导LLM下一步行动的建议指令。
    """
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    thread_id: str
    suggested_next_step: Optional[str] 