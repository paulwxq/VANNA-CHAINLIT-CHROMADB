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
            model_kwargs={
                "extra_body": {
                    "enable_thinking": False,
                    "misc": {
                        "ensure_ascii": False
                    }
                }
            }
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
        builder.add_node("prepare_tool_input", self._prepare_tool_input_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("update_state_after_tool", self._update_state_after_tool_node)
        builder.add_node("format_final_response", self._format_final_response_node)

        # 定义边
        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "prepare_tool_input",
                "end": "format_final_response"
            }
        )
        builder.add_edge("prepare_tool_input", "tools")
        builder.add_edge("tools", "update_state_after_tool")
        builder.add_edge("update_state_after_tool", "agent")
        builder.add_edge("format_final_response", END)

        # 编译图，并传入 checkpointer
        return builder.compile(checkpointer=self.checkpointer)

    def _should_continue(self, state: AgentState) -> str:
        """判断是继续调用工具还是结束。"""
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"
        return "continue"

    def _agent_node(self, state: AgentState) -> Dict[str, Any]:
        """Agent 节点：调用 LLM 进行思考和决策。"""
        logger.info(f"🧠 [Node] agent - Thread: {state['thread_id']}")
        
        messages_for_llm = list(state["messages"])
        if state.get("suggested_next_step"):
            instruction = f"基于之前的步骤，强烈建议你下一步执行 '{state['suggested_next_step']}' 操作。"
            # 为了避免污染历史，可以考虑不同的注入方式，但这里为了简单直接添加
            messages_for_llm.append(HumanMessage(content=instruction, name="system_instruction"))

        response = self.llm_with_tools.invoke(messages_for_llm)
        logger.info(f"   LLM 返回: {response.pretty_print()}")
        return {"messages": [response]}
    
    def _prepare_tool_input_node(self, state: AgentState) -> Dict[str, Any]:
        """信息组装节点：为需要上下文的工具注入历史消息。"""
        logger.info(f"🛠️ [Node] prepare_tool_input - Thread: {state['thread_id']}")
        
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {}

        # 创建一个新的 AIMessage 来替换，避免直接修改 state 中的对象
        new_tool_calls = []
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "generate_sql":
                logger.info("   检测到 generate_sql 调用，注入可序列化的历史消息。")
                # 复制一份以避免修改原始 tool_call
                modified_args = tool_call["args"].copy()
                
                # 将消息对象列表转换为可序列化的字典列表
                serializable_history = []
                for msg in state["messages"]:
                    serializable_history.append({
                        "type": msg.type,
                        "content": msg.content
                    })
                
                modified_args["history_messages"] = serializable_history
                new_tool_calls.append({
                    "name": tool_call["name"],
                    "args": modified_args,
                    "id": tool_call["id"],
                })
            else:
                new_tool_calls.append(tool_call)
        
        # 用包含修改后参数的新消息替换掉原来的
        last_message.tool_calls = new_tool_calls
        return {"messages": [last_message]}

    def _update_state_after_tool_node(self, state: AgentState) -> Dict[str, Any]:
        """流程建议与错误处理节点：在工具执行后更新状态。"""
        logger.info(f"📝 [Node] update_state_after_tool - Thread: {state['thread_id']}")
        
        last_tool_message = state['messages'][-1]
        tool_name = last_tool_message.name
        tool_output = last_tool_message.content
        next_step = None

        if tool_name == 'generate_sql':
            if "失败" in tool_output or "无法生成" in tool_output:
                next_step = 'answer_with_common_sense'
                logger.warning(f"   generate_sql 失败，建议下一步: {next_step}")
            else:
                next_step = 'valid_sql'
                logger.info(f"   generate_sql 成功，建议下一步: {next_step}")
        
        elif tool_name == 'valid_sql':
            if "失败" in tool_output:
                next_step = 'analyze_validation_error'
                logger.warning(f"   valid_sql 失败，建议下一步: {next_step}")
            else:
                next_step = 'run_sql'
                logger.info(f"   valid_sql 成功，建议下一步: {next_step}")

        elif tool_name == 'run_sql':
            next_step = 'summarize_final_answer'
            logger.info(f"   run_sql 执行完毕，建议下一步: {next_step}")

        return {"suggested_next_step": next_step}

    def _format_final_response_node(self, state: AgentState) -> Dict[str, Any]:
        """最终输出格式化节点（当前为占位符）。"""
        logger.info(f"🎨 [Node] format_final_response - Thread: {state['thread_id']} - 准备格式化最终输出...")
        # 这里可以添加一个标记，表示这是格式化后的输出
        last_message = state['messages'][-1]
        formatted_content = f"[Formatted Output]\n{last_message.content}"
        last_message.content = formatted_content
        return {"messages": [last_message]}

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
            "suggested_next_step": None, # 初始化建议
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