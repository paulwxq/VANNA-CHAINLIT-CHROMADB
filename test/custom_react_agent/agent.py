"""
基于 StateGraph 的、具备上下文感知能力的 React Agent 核心实现
"""
import logging
import json
import pandas as pd
from typing import List, Optional, Dict, Any, Tuple
from contextlib import AsyncExitStack

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from redis.asyncio import Redis
try:
    from langgraph.checkpoint.redis import AsyncRedisSaver
except ImportError:
    AsyncRedisSaver = None

# 从新模块导入配置、状态和工具
from . import config
from .state import AgentState
from .sql_tools import sql_tools

logger = logging.getLogger(__name__)

class CustomReactAgent:
    """
    一个使用 StateGraph 构建的、具备上下文感知和持久化能力的 Agent。
    """
    def __init__(self):
        """私有构造函数，请使用 create() 类方法来创建实例。"""
        self.llm = None
        self.tools = None
        self.agent_executor = None
        self.checkpointer = None
        self._exit_stack = None

    @classmethod
    async def create(cls):
        """异步工厂方法，创建并初始化 CustomReactAgent 实例。"""
        instance = cls()
        await instance._async_init()
        return instance

    async def _async_init(self):
        """异步初始化所有组件。"""
        logger.info("🚀 开始初始化 CustomReactAgent...")

        # 1. 初始化 LLM
        self.llm = ChatOpenAI(
            api_key=config.QWEN_API_KEY,
            base_url=config.QWEN_BASE_URL,
            model=config.QWEN_MODEL,
            temperature=0.1,
            extra_body={"enable_thinking": False}
        )
        logger.info(f"   LLM 已初始化，模型: {config.QWEN_MODEL}")

        # 2. 绑定工具
        self.tools = sql_tools
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        logger.info(f"   已绑定 {len(self.tools)} 个工具。")

        # 3. 初始化 Redis Checkpointer
        if config.REDIS_ENABLED and AsyncRedisSaver is not None:
            try:
                self._exit_stack = AsyncExitStack()
                checkpointer_manager = AsyncRedisSaver.from_conn_string(config.REDIS_URL)
                self.checkpointer = await self._exit_stack.enter_async_context(checkpointer_manager)
                await self.checkpointer.asetup()
                logger.info(f"   AsyncRedisSaver 持久化已启用: {config.REDIS_URL}")
            except Exception as e:
                logger.error(f"   ❌ RedisSaver 初始化失败: {e}", exc_info=True)
                if self._exit_stack:
                    await self._exit_stack.aclose()
                self.checkpointer = None
        else:
            logger.warning("   Redis 持久化功能已禁用。")

        # 4. 构建 StateGraph
        self.agent_executor = self._create_graph()
        logger.info("   StateGraph 已构建并编译。")
        logger.info("✅ CustomReactAgent 初始化完成。")

    async def close(self):
        """清理资源，关闭 Redis 连接。"""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self.checkpointer = None
            logger.info("✅ RedisSaver 资源已通过 AsyncExitStack 释放。")

    def _create_graph(self):
        """定义并编译 StateGraph。"""
        builder = StateGraph(AgentState)

        # 定义节点
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", ToolNode(self.tools))

        # 定义边
        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END}
        )
        builder.add_edge("tools", "agent")

        # 编译图，并传入 checkpointer
        return builder.compile(checkpointer=self.checkpointer)

    def _should_continue(self, state: AgentState) -> str:
        """判断是否需要继续调用工具。"""
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"
        return "continue"

    def _agent_node(self, state: AgentState) -> Dict[str, Any]:
        """Agent 节点：调用 LLM 进行思考和决策。"""
        logger.info(f"🧠 [Node] agent - Thread: {state['thread_id']}")
        
        # LangChain 会自动从 state 中提取 messages 传递给 LLM
        response = self.llm_with_tools.invoke(state["messages"])
        logger.info(f"   LLM 返回: {response.pretty_print()}")
        return {"messages": [response]}

    async def chat(self, message: str, user_id: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户聊天请求。
        """
        if not thread_id:
            thread_id = f"{user_id}:{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}"
            logger.info(f"🆕 新建会话，Thread ID: {thread_id}")

        config = {"configurable": {"thread_id": thread_id}}
        
        # 定义输入
        inputs = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "thread_id": thread_id,
        }

        final_state = None
        try:
            logger.info(f"🔄 开始处理 - Thread: {thread_id}, User: {user_id}, Message: '{message}'")
            # 使用 ainvoke 来执行完整的图流程
            final_state = await self.agent_executor.ainvoke(inputs, config)
            
            if final_state and final_state.get("messages"):
                answer = final_state["messages"][-1].content
                logger.info(f"✅ 处理完成 - Thread: {thread_id}, Final Answer: '{answer}'")
                return {"success": True, "answer": answer, "thread_id": thread_id}
            else:
                 logger.error(f"❌ 处理异常结束，最终状态为空 - Thread: {thread_id}")
                 return {"success": False, "error": "Agent failed to produce a final answer.", "thread_id": thread_id}

        except Exception as e:
            logger.error(f"❌ 处理过程中发生严重错误 - Thread: {thread_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e), "thread_id": thread_id}

    async def get_conversation_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """从 checkpointer 获取指定线程的对话历史。"""
        if not self.checkpointer:
            return []
        
        config = {"configurable": {"thread_id": thread_id}}
        conversation_state = await self.checkpointer.get(config)
        
        if not conversation_state:
            return []
            
        history = []
        for msg in conversation_state['values'].get('messages', []):
            if isinstance(msg, HumanMessage):
                role = "human"
            elif isinstance(msg, ToolMessage):
                role = "tool"
            else: # AIMessage
                role = "ai"
            
            history.append({
                "type": role,
                "content": msg.content,
                "tool_calls": getattr(msg, 'tool_calls', None)
            })
        return history 