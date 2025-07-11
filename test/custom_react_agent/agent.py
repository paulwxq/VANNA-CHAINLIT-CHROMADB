"""
基于 StateGraph 的、具备上下文感知能力的 React Agent 核心实现
"""
import logging
import json
import pandas as pd
from typing import List, Optional, Dict, Any, Tuple
from contextlib import AsyncExitStack

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from redis.asyncio import Redis
try:
    from langgraph.checkpoint.redis import AsyncRedisSaver
except ImportError:
    AsyncRedisSaver = None

# 从新模块导入配置、状态和工具
try:
    # 尝试相对导入（当作为模块导入时）
    from . import config
    from .state import AgentState
    from .sql_tools import sql_tools
except ImportError:
    # 如果相对导入失败，尝试绝对导入（直接运行时）
    import config
    from state import AgentState
    from sql_tools import sql_tools
from langchain_core.runnables import RunnablePassthrough

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
            extra_body={
                "enable_thinking": False,
                "misc": {
                    "ensure_ascii": False
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
        """定义并编译最终的、正确的 StateGraph 结构。"""
        builder = StateGraph(AgentState)

        # 定义所有需要的节点
        builder.add_node("agent", self._agent_node)
        builder.add_node("prepare_tool_input", self._prepare_tool_input_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("update_state_after_tool", self._update_state_after_tool_node)
        builder.add_node("format_final_response", self._format_final_response_node)

        # 建立正确的边连接
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

        return builder.compile(checkpointer=self.checkpointer)

    def _should_continue(self, state: AgentState) -> str:
        """判断是继续调用工具还是结束。"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        return "end"

    def _agent_node(self, state: AgentState) -> Dict[str, Any]:
        """Agent 节点：只负责调用 LLM 并返回其输出。"""
        logger.info(f"🧠 [Node] agent - Thread: {state['thread_id']}")
        
        messages_for_llm = list(state["messages"])
        if state.get("suggested_next_step"):
            instruction = f"提示：建议下一步使用工具 '{state['suggested_next_step']}'。"
            messages_for_llm.append(SystemMessage(content=instruction))

        response = self.llm_with_tools.invoke(messages_for_llm)
        logger.info(f"   LLM Response: {response.pretty_print()}")
        
        # 只返回消息，不承担其他职责
        return {"messages": [response]}
    
    def _print_state_info(self, state: AgentState, node_name: str) -> None:
        """
        打印 state 的全部信息，用于调试
        """
        logger.info(" ~" * 10 + " State Print Start" + " ~" * 10)
        logger.info(f"📋 [State Debug] {node_name} - 当前状态信息:")
        
        # 🎯 打印 state 中的所有字段
        logger.info("   State中的所有字段:")
        for key, value in state.items():
            if key == "messages":
                logger.info(f"     {key}: {len(value)} 条消息")
            else:
                logger.info(f"     {key}: {value}")
        
        # 原有的详细消息信息
        logger.info(f"   用户ID: {state.get('user_id', 'N/A')}")
        logger.info(f"   线程ID: {state.get('thread_id', 'N/A')}")
        logger.info(f"   建议下一步: {state.get('suggested_next_step', 'N/A')}")
        
        messages = state.get("messages", [])
        logger.info(f"   消息历史数量: {len(messages)}")
        
        if messages:
            logger.info("   最近的消息:")
            for i, msg in enumerate(messages[-10:], start=max(0, len(messages)-10)):  # 显示最后3条消息
                msg_type = type(msg).__name__
                content_preview = str(msg.content)[:100] + "..." if len(str(msg.content)) > 100 else str(msg.content)
                logger.info(f"     [{i}] {msg_type}: {content_preview}")
                
                # 如果是 AIMessage 且有工具调用，显示工具调用信息
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', 'Unknown')
                        tool_args = tool_call.get('args', {})
                        logger.info(f"         工具调用: {tool_name}")
                        logger.info(f"         参数: {str(tool_args)[:200]}...")
        
        logger.info(" ~" * 10 + " State Print End" + " ~" * 10)

    def _prepare_tool_input_node(self, state: AgentState) -> Dict[str, Any]:
        """
        信息组装节点：为需要上下文的工具注入历史消息。
        """
        logger.info(f"🛠️ [Node] prepare_tool_input - Thread: {state['thread_id']}")
        
        # 🎯 打印 state 全部信息
        # self._print_state_info(state, "prepare_tool_input")
        
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {"messages": [last_message]}

        # 创建一个新的 AIMessage 来替换，避免直接修改 state 中的对象
        new_tool_calls = []
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "generate_sql":
                logger.info("   检测到 generate_sql 调用，注入历史消息。")
                # 复制一份以避免修改原始 tool_call
                modified_args = tool_call["args"].copy()
                
                # 🎯 改进的消息过滤逻辑：只保留有用的对话上下文，排除当前问题
                clean_history = []
                messages_except_current = state["messages"][:-1]  # 排除最后一个消息（当前问题）
                
                for msg in messages_except_current:
                    if isinstance(msg, HumanMessage):
                        # 保留历史用户消息（但不包括当前问题）
                        clean_history.append({
                            "type": "human",
                            "content": msg.content
                        })
                    elif isinstance(msg, AIMessage):
                        # 只保留最终的、面向用户的回答（包含"[Formatted Output]"的消息）
                        if msg.content and "[Formatted Output]" in msg.content:
                            # 去掉 "[Formatted Output]" 标记，只保留真正的回答
                            clean_content = msg.content.replace("[Formatted Output]\n", "")
                            clean_history.append({
                                "type": "ai",
                                "content": clean_content
                            })
                        # 跳过包含工具调用的 AIMessage（中间步骤）
                    # 跳过所有 ToolMessage（工具执行结果）
                
                modified_args["history_messages"] = clean_history
                logger.info(f"   注入了 {len(clean_history)} 条过滤后的历史消息")
                
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
        """在工具执行后，更新 suggested_next_step 并清理参数。"""
        logger.info(f"📝 [Node] update_state_after_tool - Thread: {state['thread_id']}")
        
        # 🎯 打印 state 全部信息
        self._print_state_info(state, "update_state_after_tool")
        
        last_tool_message = state['messages'][-1]
        tool_name = last_tool_message.name
        tool_output = last_tool_message.content
        next_step = None

        if tool_name == 'generate_sql':
            if "失败" in tool_output or "无法生成" in tool_output:
                next_step = 'answer_with_common_sense'
            else:
                next_step = 'valid_sql'
            
            # 🎯 清理 generate_sql 的 history_messages 参数，设置为空字符串
            # self._clear_history_messages_parameter(state['messages'])
        
        elif tool_name == 'valid_sql':
            if "失败" in tool_output:
                next_step = 'analyze_validation_error'
            else:
                next_step = 'run_sql'

        elif tool_name == 'run_sql':
            next_step = 'summarize_final_answer'
            
        logger.info(f"   Tool '{tool_name}' executed. Suggested next step: {next_step}")
        return {"suggested_next_step": next_step}

    def _clear_history_messages_parameter(self, messages: List[BaseMessage]) -> None:
        """
        将 generate_sql 工具的 history_messages 参数设置为空字符串
        """
        for message in messages:
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call["name"] == "generate_sql" and "history_messages" in tool_call["args"]:
                        tool_call["args"]["history_messages"] = ""
                        logger.info(f"   已将 generate_sql 的 history_messages 设置为空字符串")

    def _format_final_response_node(self, state: AgentState) -> Dict[str, Any]:
        """最终输出格式化节点。"""
        logger.info(f"🎨 [Node] format_final_response - Thread: {state['thread_id']}")
        
        # 保持原有的消息格式化（用于shell.py兼容）
        last_message = state['messages'][-1]
        last_message.content = f"[Formatted Output]\n{last_message.content}"
        
        # 生成API格式的数据
        api_data = self._generate_api_data(state)

        # 打印api_data
        print("-"*20+"api_data_start"+"-"*20)
        print(api_data)
        print("-"*20+"api_data_end"+"-"*20)

        return {
            "messages": [last_message],
            "api_data": api_data  # 新增：API格式数据
        }

    def _generate_api_data(self, state: AgentState) -> Dict[str, Any]:
        """生成API格式的数据结构"""
        logger.info("📊 生成API格式数据...")
        
        # 提取基础响应内容
        last_message = state['messages'][-1]
        response_content = last_message.content
        
        # 去掉格式化标记，获取纯净的回答
        if response_content.startswith("[Formatted Output]\n"):
            response_content = response_content.replace("[Formatted Output]\n", "")
        
        # 初始化API数据结构
        api_data = {
            "response": response_content
        }
        
        # 提取SQL和数据记录
        sql_info = self._extract_sql_and_data(state['messages'])
        if sql_info['sql']:
            api_data["sql"] = sql_info['sql']
        if sql_info['records']:
            api_data["records"] = sql_info['records']
        
        # 生成Agent元数据
        api_data["react_agent_meta"] = self._collect_agent_metadata(state)
        
        logger.info(f"   API数据生成完成，包含字段: {list(api_data.keys())}")
        return api_data

    def _extract_sql_and_data(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """从消息历史中提取SQL和数据记录"""
        result = {"sql": None, "records": None}
        
        # 查找最后一个HumanMessage之后的工具执行结果
        last_human_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_index = i
                break
        
        if last_human_index == -1:
            return result
        
        # 在当前对话轮次中查找工具执行结果
        current_conversation = messages[last_human_index:]
        
        sql_query = None
        sql_data = None
        
        for msg in current_conversation:
            if isinstance(msg, ToolMessage):
                if msg.name == 'generate_sql':
                    # 提取生成的SQL
                    content = msg.content
                    if content and not any(keyword in content for keyword in ["失败", "无法生成", "Database query failed"]):
                        sql_query = content.strip()
                        
                elif msg.name == 'run_sql':
                    # 提取SQL执行结果
                    try:
                        import json
                        parsed_data = json.loads(msg.content)
                        if isinstance(parsed_data, list) and len(parsed_data) > 0:
                            # DataFrame.to_json(orient='records') 格式
                            columns = list(parsed_data[0].keys()) if parsed_data else []
                            sql_data = {
                                "columns": columns,
                                "rows": parsed_data,
                                "total_row_count": len(parsed_data),
                                "is_limited": False  # 当前版本没有实现限制
                            }
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"   解析SQL结果失败: {e}")
        
        if sql_query:
            result["sql"] = sql_query
        if sql_data:
            result["records"] = sql_data
            
        return result

    def _collect_agent_metadata(self, state: AgentState) -> Dict[str, Any]:
        """收集Agent元数据"""
        messages = state['messages']
        
        # 统计工具使用情况
        tools_used = []
        sql_execution_count = 0
        context_injected = False
        
        # 计算对话轮次（HumanMessage的数量）
        conversation_rounds = sum(1 for msg in messages if isinstance(msg, HumanMessage))
        
        # 分析工具调用和执行
        for msg in messages:
            if isinstance(msg, ToolMessage):
                if msg.name not in tools_used:
                    tools_used.append(msg.name)
                if msg.name == 'run_sql':
                    sql_execution_count += 1
            elif isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get('name')
                    if tool_name and tool_name not in tools_used:
                        tools_used.append(tool_name)
                    
                    # 检查是否注入了历史上下文
                    if (tool_name == 'generate_sql' and 
                        tool_call.get('args', {}).get('history_messages')):
                        context_injected = True
        
        # 构建执行路径（简化版本）
        execution_path = ["agent"]
        if tools_used:
            execution_path.extend(["prepare_tool_input", "tools"])
        execution_path.append("format_final_response")
        
        return {
            "thread_id": state['thread_id'],
            "conversation_rounds": conversation_rounds,
            "tools_used": tools_used,
            "execution_path": execution_path,
            "total_messages": len(messages),
            "sql_execution_count": sql_execution_count,
            "context_injected": context_injected,
            "agent_version": "custom_react_v1"
        }

    def _extract_latest_sql_data(self, messages: List[BaseMessage]) -> Optional[str]:
        """从消息历史中提取最近的run_sql执行结果，但仅限于当前对话轮次。"""
        logger.info("🔍 提取最新的SQL执行结果...")
        
        # 🎯 只查找最后一个HumanMessage之后的SQL执行结果
        last_human_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_index = i
                break
        
        if last_human_index == -1:
            logger.info("   未找到用户消息，跳过SQL数据提取")
            return None
        
        # 只在当前对话轮次中查找SQL结果
        current_conversation = messages[last_human_index:]
        logger.info(f"   当前对话轮次包含 {len(current_conversation)} 条消息")
        
        for msg in reversed(current_conversation):
            if isinstance(msg, ToolMessage) and msg.name == 'run_sql':
                logger.info(f"   找到当前对话轮次的run_sql结果: {msg.content[:100]}...")
                
                # 🎯 处理Unicode转义序列，将其转换为正常的中文字符
                try:
                    # 先尝试解析JSON以验证格式
                    parsed_data = json.loads(msg.content)
                    # 重新序列化，确保中文字符正常显示
                    formatted_content = json.dumps(parsed_data, ensure_ascii=False, separators=(',', ':'))
                    logger.info(f"   已转换Unicode转义序列为中文字符")
                    return formatted_content
                except json.JSONDecodeError:
                    # 如果不是有效JSON，直接返回原内容
                    logger.warning(f"   SQL结果不是有效JSON格式，返回原始内容")
                    return msg.content
        
        logger.info("   当前对话轮次中未找到run_sql执行结果")
        return None

    async def chat(self, message: str, user_id: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户聊天请求。
        """
        if not thread_id:
            now = pd.Timestamp.now()
            milliseconds = int(now.microsecond / 1000)
            thread_id = f"{user_id}:{now.strftime('%Y%m%d%H%M%S')}{milliseconds:03d}"
            logger.info(f"🆕 新建会话，Thread ID: {thread_id}")
        
        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }
        
        inputs = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "thread_id": thread_id,
            "suggested_next_step": None,
        }

        try:
            final_state = await self.agent_executor.ainvoke(inputs, config)
            answer = final_state["messages"][-1].content
            
            # 🎯 提取最近的 run_sql 执行结果（不修改messages）
            sql_data = self._extract_latest_sql_data(final_state["messages"])
            
            logger.info(f"✅ 处理完成 - Final Answer: '{answer}'")
            
            # 构建返回结果（保持简化格式用于shell.py）
            result = {
                "success": True, 
                "answer": answer, 
                "thread_id": thread_id
            }
            
            # 只有当存在SQL数据时才添加到返回结果中
            if sql_data:
                result["sql_data"] = sql_data
                logger.info("   📊 已包含SQL原始数据")
            
            # 🎯 如果存在API格式数据，也添加到返回结果中（用于API层）
            if "api_data" in final_state:
                result["api_data"] = final_state["api_data"]
                logger.info("   🔌 已包含API格式数据")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 处理过程中发生严重错误 - Thread: {thread_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e), "thread_id": thread_id}
    
    async def get_conversation_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """从 checkpointer 获取指定线程的对话历史。"""
        if not self.checkpointer:
            return []
        
        config = {"configurable": {"thread_id": thread_id}}
        try:
            conversation_state = await self.checkpointer.aget(config)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"⚠️ Event loop已关闭，尝试重新获取对话历史: {thread_id}")
                # 如果事件循环关闭，返回空结果而不是抛出异常
                return []
            else:
                raise
        
        if not conversation_state:
            return []
            
        history = []
        messages = conversation_state.get('channel_values', {}).get('messages', [])
        for msg in messages:
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

    async def get_user_recent_conversations(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取指定用户的最近聊天记录列表
        利用thread_id格式 'user_id:timestamp' 来查询
        """
        if not self.checkpointer:
            return []
        
        try:
            # 创建Redis连接 - 使用与checkpointer相同的连接配置
            from redis.asyncio import Redis
            redis_client = Redis.from_url(config.REDIS_URL, decode_responses=True)
            
            # 1. 扫描匹配该用户的所有checkpoint keys
            # checkpointer的key格式通常是: checkpoint:thread_id:checkpoint_id
            pattern = f"checkpoint:{user_id}:*"
            logger.info(f"🔍 扫描模式: {pattern}")
            
            user_threads = {}
            cursor = 0
            
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=1000
                )
                

                
                for key in keys:
                    try:
                        # 解析key获取thread_id和checkpoint信息
                        # key格式: checkpoint:user_id:timestamp:status:checkpoint_id
                        key_str = key.decode() if isinstance(key, bytes) else key
                        parts = key_str.split(':')
                        
                        if len(parts) >= 4:
                            # thread_id = user_id:timestamp
                            thread_id = f"{parts[1]}:{parts[2]}"
                            timestamp = parts[2]
                            
                            # 跟踪每个thread的最新checkpoint
                            if thread_id not in user_threads:
                                user_threads[thread_id] = {
                                    "thread_id": thread_id,
                                    "timestamp": timestamp,
                                    "latest_key": key_str
                                }
                            else:
                                # 保留最新的checkpoint key（通常checkpoint_id越大越新）
                                if len(parts) > 4 and parts[4] > user_threads[thread_id]["latest_key"].split(':')[4]:
                                    user_threads[thread_id]["latest_key"] = key_str
                                    
                    except Exception as e:
                        logger.warning(f"解析key {key} 失败: {e}")
                        continue
                
                if cursor == 0:
                    break
            
            # 关闭临时Redis连接
            await redis_client.close()
            
            # 2. 按时间戳排序（新的在前）
            sorted_threads = sorted(
                user_threads.values(),
                key=lambda x: x["timestamp"],
                reverse=True
            )[:limit]
            
            # 3. 获取每个thread的详细信息
            conversations = []
            for thread_info in sorted_threads:
                try:
                    thread_id = thread_info["thread_id"]
                    thread_config = {"configurable": {"thread_id": thread_id}}
                    
                    try:
                        state = await self.checkpointer.aget(thread_config)
                    except RuntimeError as e:
                        if "Event loop is closed" in str(e):
                            logger.warning(f"⚠️ Event loop已关闭，跳过thread: {thread_id}")
                            continue
                        else:
                            raise
                    
                    if state and state.get('channel_values', {}).get('messages'):
                        messages = state['channel_values']['messages']
                        
                        # 生成对话预览
                        preview = self._generate_conversation_preview(messages)
                        
                        conversations.append({
                            "thread_id": thread_id,
                            "user_id": user_id,
                            "timestamp": thread_info["timestamp"],
                            "message_count": len(messages),
                            "last_message": messages[-1].content if messages else None,
                            "last_updated": state.get('created_at'),
                            "conversation_preview": preview,
                            "formatted_time": self._format_timestamp(thread_info["timestamp"])
                        })
                        
                except Exception as e:
                    logger.error(f"获取thread {thread_info['thread_id']} 详情失败: {e}")
                    continue
            
            logger.info(f"✅ 找到用户 {user_id} 的 {len(conversations)} 个对话")
            return conversations
            
        except Exception as e:
            logger.error(f"❌ 获取用户 {user_id} 对话列表失败: {e}")
            return []

    def _generate_conversation_preview(self, messages: List[BaseMessage]) -> str:
        """生成对话预览"""
        if not messages:
            return "空对话"
        
        # 获取第一个用户消息作为预览
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = str(msg.content)
                return content[:50] + "..." if len(content) > 50 else content
        
        return "系统消息"

    def _format_timestamp(self, timestamp: str) -> str:
        """格式化时间戳为可读格式"""
        try:
            # timestamp格式: 20250710123137984
            if len(timestamp) >= 14:
                year = timestamp[:4]
                month = timestamp[4:6]
                day = timestamp[6:8]
                hour = timestamp[8:10]
                minute = timestamp[10:12]
                second = timestamp[12:14]
                return f"{year}-{month}-{day} {hour}:{minute}:{second}"
        except Exception:
            pass
        return timestamp 