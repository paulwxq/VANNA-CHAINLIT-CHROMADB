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
    """
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    thread_id: str 