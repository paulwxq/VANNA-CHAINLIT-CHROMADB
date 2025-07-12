"""
基于 StateGraph 的、具备上下文感知能力的 React Agent 核心实现
"""
import logging
import json
import pandas as pd
import httpx
from typing import List, Optional, Dict, Any, Tuple
from contextlib import AsyncExitStack

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import redis.asyncio as redis
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
        self.redis_client = None

    @classmethod
    async def create(cls):
        """异步工厂方法，创建并初始化 CustomReactAgent 实例。"""
        instance = cls()
        await instance._async_init()
        return instance

    async def _async_init(self):
        """异步初始化所有组件。"""
        logger.info("🚀 开始初始化 CustomReactAgent...")

        # 1. 初始化异步Redis客户端
        self.redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            await self.redis_client.ping()
            logger.info(f"   ✅ Redis连接成功: {config.REDIS_URL}")
        except Exception as e:
            logger.error(f"   ❌ Redis连接失败: {e}")
            raise

        # 2. 初始化 LLM
        self.llm = ChatOpenAI(
            api_key=config.QWEN_API_KEY,
            base_url=config.QWEN_BASE_URL,
            model=config.QWEN_MODEL,
            temperature=0.1,
            timeout=config.NETWORK_TIMEOUT,  # 添加超时配置
            max_retries=0,  # 禁用OpenAI客户端重试，改用Agent层统一重试
            extra_body={
                "enable_thinking": False,
                "misc": {
                    "ensure_ascii": False
                }
            },
            # 新增：优化HTTP连接配置
            http_client=httpx.Client(
                limits=httpx.Limits(
                    max_connections=config.HTTP_MAX_CONNECTIONS,
                    max_keepalive_connections=config.HTTP_MAX_KEEPALIVE_CONNECTIONS,
                    keepalive_expiry=config.HTTP_KEEPALIVE_EXPIRY,  # 30秒keep-alive过期
                ),
                timeout=httpx.Timeout(
                    connect=config.HTTP_CONNECT_TIMEOUT,   # 连接超时
                    read=config.NETWORK_TIMEOUT,           # 读取超时
                    write=config.HTTP_CONNECT_TIMEOUT,     # 写入超时
                    pool=config.HTTP_POOL_TIMEOUT          # 连接池超时
                )
            )
        )
        logger.info(f"   LLM 已初始化，模型: {config.QWEN_MODEL}")

        # 3. 绑定工具
        self.tools = sql_tools
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        logger.info(f"   已绑定 {len(self.tools)} 个工具。")

        # 4. 初始化 Redis Checkpointer
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

        # 5. 构建 StateGraph
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
        
        if self.redis_client:
            await self.redis_client.aclose()
            logger.info("✅ Redis客户端已关闭。")

    def _create_graph(self):
        """定义并编译最终的、正确的 StateGraph 结构。"""
        builder = StateGraph(AgentState)

        # 定义所有需要的节点 - 全部改为异步
        builder.add_node("agent", self._async_agent_node)
        builder.add_node("prepare_tool_input", self._async_prepare_tool_input_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("update_state_after_tool", self._async_update_state_after_tool_node)
        builder.add_node("format_final_response", self._async_format_final_response_node)

        # 建立正确的边连接
        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._async_should_continue,
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

    async def _async_should_continue(self, state: AgentState) -> str:
        """异步判断是继续调用工具还是结束。"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        return "end"

    async def _async_agent_node(self, state: AgentState) -> Dict[str, Any]:
        """异步Agent 节点：使用异步LLM调用。"""
        logger.info(f"🧠 [Async Node] agent - Thread: {state['thread_id']}")
        
        messages_for_llm = list(state["messages"])
        
        # 🎯 添加数据库范围系统提示词（仅在对话开始时添加）
        if len(state["messages"]) == 1 and isinstance(state["messages"][0], HumanMessage):
            db_scope_prompt = self._get_database_scope_prompt()
            if db_scope_prompt:
                messages_for_llm.insert(0, SystemMessage(content=db_scope_prompt))
                logger.info("   ✅ 已添加数据库范围判断提示词")
        
        # 检查是否需要分析验证错误
        next_step = state.get("suggested_next_step")
        if next_step == "analyze_validation_error":
            # 查找最近的 valid_sql 错误信息
            for msg in reversed(state["messages"]):
                if isinstance(msg, ToolMessage) and msg.name == "valid_sql":
                    error_guidance = self._generate_validation_error_guidance(msg.content)
                    messages_for_llm.append(SystemMessage(content=error_guidance))
                    logger.info("   ✅ 已添加SQL验证错误指导")
                    break
        elif next_step and next_step != "analyze_validation_error":
            instruction = f"Suggestion: Consider using the '{next_step}' tool for the next step."
            messages_for_llm.append(SystemMessage(content=instruction))

        # 添加重试机制处理网络连接问题
        import asyncio
        max_retries = config.MAX_RETRIES
        for attempt in range(max_retries):
            try:
                # 使用异步调用
                response = await self.llm_with_tools.ainvoke(messages_for_llm)
                
                # 新增：详细的响应检查和日志
                logger.info(f"   LLM原始响应内容: '{response.content}'")
                logger.info(f"   响应内容长度: {len(response.content) if response.content else 0}")
                logger.info(f"   响应内容类型: {type(response.content)}")
                logger.info(f"   LLM是否有工具调用: {hasattr(response, 'tool_calls') and response.tool_calls}")

                if hasattr(response, 'tool_calls') and response.tool_calls:
                    logger.info(f"   工具调用数量: {len(response.tool_calls)}")
                    for i, tool_call in enumerate(response.tool_calls):
                        logger.info(f"   工具调用[{i}]: {tool_call.get('name', 'Unknown')}")

                # 🎯 改进的响应检查和重试逻辑
                # 检查空响应情况 - 将空响应也视为需要重试的情况
                if not response.content and not (hasattr(response, 'tool_calls') and response.tool_calls):
                    logger.warning("   ⚠️ LLM返回空响应且无工具调用")
                    if attempt < max_retries - 1:
                        # 空响应也进行重试
                        wait_time = config.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(f"   🔄 空响应重试，{wait_time}秒后重试...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # 所有重试都失败，返回降级回答
                        logger.error(f"   ❌ 多次尝试仍返回空响应，返回降级回答")
                        fallback_content = "抱歉，我现在无法正确处理您的问题。请稍后重试或重新表述您的问题。"
                        fallback_response = AIMessage(content=fallback_content)
                        return {"messages": [fallback_response]}
                        
                elif response.content and response.content.strip() == "":
                    logger.warning("   ⚠️ LLM返回只包含空白字符的内容")
                    if attempt < max_retries - 1:
                        # 空白字符也进行重试
                        wait_time = config.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(f"   🔄 空白字符重试，{wait_time}秒后重试...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # 所有重试都失败，返回降级回答
                        logger.error(f"   ❌ 多次尝试仍返回空白字符，返回降级回答")
                        fallback_content = "抱歉，我现在无法正确处理您的问题。请稍后重试或重新表述您的问题。"
                        fallback_response = AIMessage(content=fallback_content)
                        return {"messages": [fallback_response]}
                        
                elif not response.content and hasattr(response, 'tool_calls') and response.tool_calls:
                    logger.info("   ✅ LLM只返回工具调用，无文本内容（正常情况）")
                    
                # 🎯 最终检查：确保响应是有效的
                if ((response.content and response.content.strip()) or 
                    (hasattr(response, 'tool_calls') and response.tool_calls)):
                    logger.info(f"   ✅ 异步LLM调用成功，返回有效响应")
                    return {"messages": [response]}
                else:
                    # 这种情况理论上不应该发生，但作为最后的保障
                    logger.error(f"   ❌ 意外的响应格式，进行重试")
                    if attempt < max_retries - 1:
                        wait_time = config.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(f"   🔄 意外响应格式重试，{wait_time}秒后重试...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        fallback_content = "抱歉，我现在无法正确处理您的问题。请稍后重试或重新表述您的问题。"
                        fallback_response = AIMessage(content=fallback_content)
                        return {"messages": [fallback_response]}
                
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                logger.warning(f"   ⚠️ LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {error_type}: {error_msg}")
                
                # 🎯 改进的错误分类逻辑：检查异常类型和错误消息
                is_network_error = False
                is_parameter_error = False
                
                # 1. 检查异常类型
                network_exception_types = [
                    'APIConnectionError', 'ConnectTimeout', 'ReadTimeout', 
                    'TimeoutError', 'APITimeoutError', 'ConnectError', 
                    'HTTPError', 'RequestException', 'ConnectionError'
                ]
                if error_type in network_exception_types:
                    is_network_error = True
                    logger.info(f"   📊 根据异常类型判断为网络错误: {error_type}")
                
                # 2. 检查BadRequestError中的参数错误
                if error_type == 'BadRequestError':
                    # 检查是否是消息格式错误
                    if any(keyword in error_msg.lower() for keyword in [
                        'must be followed by tool messages',
                        'invalid_parameter_error',
                        'assistant message with "tool_calls"',
                        'tool_call_id',
                        'message format'
                    ]):
                        is_parameter_error = True
                        logger.info(f"   📊 根据错误消息判断为参数格式错误: {error_msg[:100]}...")
                
                # 3. 检查错误消息内容（不区分大小写）
                error_msg_lower = error_msg.lower()
                network_keywords = [
                    'connection error', 'connect error', 'timeout', 'timed out',
                    'network', 'connection refused', 'connection reset',
                    'remote host', '远程主机', '网络连接', '连接超时',
                    'request timed out', 'read timeout', 'connect timeout'
                ]
                
                for keyword in network_keywords:
                    if keyword in error_msg_lower:
                        is_network_error = True
                        logger.info(f"   📊 根据错误消息判断为网络错误: '{keyword}' in '{error_msg}'")
                        break
                
                # 处理可重试的错误
                if is_network_error or is_parameter_error:
                    if attempt < max_retries - 1:
                        # 渐进式重试间隔：3, 6, 12秒
                        wait_time = config.RETRY_BASE_DELAY * (2 ** attempt)
                        error_type_desc = "网络错误" if is_network_error else "参数格式错误"
                        logger.info(f"   🔄 {error_type_desc}，{wait_time}秒后重试...")
                        
                        # 🎯 对于参数错误，修复消息历史后重试
                        if is_parameter_error:
                            try:
                                messages_for_llm = await self._handle_parameter_error_with_retry(
                                    messages_for_llm, error_msg, attempt
                                )
                                logger.info(f"   🔧 消息历史修复完成，继续重试...")
                            except Exception as fix_error:
                                logger.error(f"   ❌ 消息历史修复失败: {fix_error}")
                                # 修复失败，使用原始消息继续重试
                        
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # 所有重试都失败了，返回一个降级的回答
                        error_type_desc = "网络连接" if is_network_error else "请求格式"
                        logger.error(f"   ❌ {error_type_desc}持续失败，返回降级回答")
                        
                        # 检查是否有SQL执行结果可以利用
                        sql_data = await self._async_extract_latest_sql_data(state["messages"])
                        if sql_data:
                            fallback_content = f"抱歉，由于{error_type_desc}问题，无法生成完整的文字总结。不过查询已成功执行，结果如下：\n\n" + sql_data
                        else:
                            fallback_content = f"抱歉，由于{error_type_desc}问题，无法完成此次请求。请稍后重试或检查网络连接。"
                            
                        fallback_response = AIMessage(content=fallback_content)
                        return {"messages": [fallback_response]}
                else:
                    # 非网络错误，直接抛出
                    logger.error(f"   ❌ LLM调用出现非可重试错误: {error_type}: {error_msg}")
                    raise e
    
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
            for i, msg in enumerate(messages[-10:], start=max(0, len(messages)-10)):  # 显示最后10条消息
                msg_type = type(msg).__name__
                content = str(msg.content)
                
                # 对于长内容，使用多行显示
                if len(content) > 200:
                    logger.info(f"     [{i}] {msg_type}:")
                    logger.info(f"         {content}")
                else:
                    logger.info(f"     [{i}] {msg_type}: {content}")
                
                # 如果是 AIMessage 且有工具调用，显示工具调用信息
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', 'Unknown')
                        tool_args = tool_call.get('args', {})
                        logger.info(f"         工具调用: {tool_name}")
                        
                        # 对于复杂参数，使用JSON格式化
                        import json
                        try:
                            formatted_args = json.dumps(tool_args, ensure_ascii=False, indent=2)
                            logger.info(f"         参数:")
                            for line in formatted_args.split('\n'):
                                logger.info(f"           {line}")
                        except Exception:
                            logger.info(f"         参数: {str(tool_args)}")
        
        logger.info(" ~" * 10 + " State Print End" + " ~" * 10)

    async def _async_prepare_tool_input_node(self, state: AgentState) -> Dict[str, Any]:
        """
        异步信息组装节点：为需要上下文的工具注入历史消息。
        """
        logger.info(f"🛠️ [Async Node] prepare_tool_input - Thread: {state['thread_id']}")
        
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

    async def _async_update_state_after_tool_node(self, state: AgentState) -> Dict[str, Any]:
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

    async def _async_format_final_response_node(self, state: AgentState) -> Dict[str, Any]:
        """异步最终输出格式化节点。"""
        logger.info(f"🎨 [Async Node] format_final_response - Thread: {state['thread_id']}")
        
        # 保持原有的消息格式化（用于shell.py兼容）
        last_message = state['messages'][-1]
        last_message.content = f"[Formatted Output]\n{last_message.content}"
        
        # 生成API格式的数据
        api_data = await self._async_generate_api_data(state)

        # 打印api_data
        print("-"*20+"api_data_start"+"-"*20)
        print(api_data)
        print("-"*20+"api_data_end"+"-"*20)

        return {
            "messages": [last_message],
            "api_data": api_data  # 新增：API格式数据
        }

    async def _async_generate_api_data(self, state: AgentState) -> Dict[str, Any]:
        """异步生成API格式的数据结构"""
        logger.info("📊 异步生成API格式数据...")
        
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
        sql_info = await self._async_extract_sql_and_data(state['messages'])
        if sql_info['sql']:
            api_data["sql"] = sql_info['sql']
        if sql_info['records']:
            api_data["records"] = sql_info['records']
        
        # 生成Agent元数据
        api_data["react_agent_meta"] = await self._async_collect_agent_metadata(state)
        
        logger.info(f"   API数据生成完成，包含字段: {list(api_data.keys())}")
        return api_data

    async def _async_extract_sql_and_data(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """异步从消息历史中提取SQL和数据记录"""
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

    async def _async_collect_agent_metadata(self, state: AgentState) -> Dict[str, Any]:
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

    async def _async_extract_latest_sql_data(self, messages: List[BaseMessage]) -> Optional[str]:
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
            sql_data = await self._async_extract_latest_sql_data(final_state["messages"])
            
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
            # 使用统一的异步Redis客户端
            redis_client = self.redis_client
            
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

    def _get_database_scope_prompt(self) -> str:
        """Get database scope prompt for intelligent query decision making"""
        try:
            import os
            # Read agent/tools/db_query_decision_prompt.txt
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_scope_file = os.path.join(project_root, "agent", "tools", "db_query_decision_prompt.txt")
            
            with open(db_scope_file, 'r', encoding='utf-8') as f:
                db_scope_content = f.read().strip()
            
            prompt = f"""You are an intelligent database query assistant. When deciding whether to use database query tools, please follow these rules:

=== DATABASE BUSINESS SCOPE ===
{db_scope_content}

=== DECISION RULES ===
1. If the question involves data within the above business scope (service areas, branches, revenue, traffic flow, etc.), use the generate_sql tool
2. If the question is about general knowledge (like "when do lychees ripen?", weather, historical events, etc.), answer directly based on your knowledge WITHOUT using database tools
3. When answering general knowledge questions, clearly indicate that this is based on general knowledge, not database data

=== FALLBACK STRATEGY ===
When generate_sql returns an error message or when queries return no results:
1. First, check if the question is within the database scope described above
2. For questions clearly OUTSIDE the database scope (world events, general knowledge, etc.):
   - Provide the answer based on your knowledge immediately
   - CLEARLY indicate this is based on general knowledge, not database data
   - Use format: "Based on general knowledge (not database data): [answer]"
3. For questions within database scope but queries return no results:
   - If it's a reasonable question that might have a general answer, provide it
   - Still indicate the source: "Based on general knowledge (database had no results): [answer]"
4. For questions that definitely require specific database data:
   - Acknowledge the limitation and suggest the data may not be available
   - Do not attempt to guess or fabricate specific data

Please intelligently choose whether to query the database based on the nature of the user's question."""
            
            return prompt
            
        except Exception as e:
            logger.warning(f"⚠️ Unable to read database scope description file: {e}")
            return ""

    def _generate_validation_error_guidance(self, validation_error: str) -> str:
        """根据验证错误类型生成具体的修复指导"""
        
        if "字段不存在" in validation_error or "column" in validation_error.lower():
            return """SQL验证失败：字段不存在错误。
处理建议：
1. 检查字段名是否拼写正确
2. 如果字段确实不存在，请告知用户缺少该字段，并基于常识提供答案
3. 不要尝试修复不存在的字段，直接给出基于常识的解释"""

        elif "表不存在" in validation_error or "table" in validation_error.lower():
            return """SQL验证失败：表不存在错误。
处理建议：
1. 检查表名是否拼写正确
2. 如果表确实不存在，请告知用户该数据不在数据库中
3. 基于问题性质，提供常识性的答案或建议用户确认数据源"""

        elif "语法错误" in validation_error or "syntax error" in validation_error.lower():
            return """SQL验证失败：语法错误。
处理建议：
1. 仔细检查SQL语法（括号、引号、关键词等）
2. 修复语法错误后，调用 valid_sql 工具重新验证
3. 常见问题：缺少逗号、括号不匹配、关键词拼写错误"""

        else:
            return f"""SQL验证失败：{validation_error}
处理建议：
1. 如果是语法问题，请修复后重新验证
2. 如果是字段/表不存在，请向用户说明并提供基于常识的答案
3. 避免猜测或编造数据库中不存在的信息"""

    # === 参数错误诊断和修复函数 ===
    
    def _diagnose_parameter_error(self, messages: List[BaseMessage], error_msg: str) -> Dict[str, Any]:
        """
        诊断参数错误的详细原因
        """
        logger.error("🔍 开始诊断参数错误...")
        logger.error(f"   错误消息: {error_msg}")
        
        diagnosis = {
            "error_type": "parameter_error",
            "incomplete_tool_calls": [],
            "orphaned_tool_messages": [],
            "total_messages": len(messages),
            "recommended_action": None
        }
        
        # 分析消息历史
        logger.error("📋 消息历史分析:")
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            
            if isinstance(msg, AIMessage):
                has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
                content_summary = f"'{msg.content[:50]}...'" if msg.content else "空内容"
                
                logger.error(f"   [{i}] {msg_type}: {content_summary}")
                
                if has_tool_calls:
                    logger.error(f"       工具调用: {len(msg.tool_calls)} 个")
                    for j, tc in enumerate(msg.tool_calls):
                        tool_name = tc.get('name', 'Unknown')
                        tool_id = tc.get('id', 'Unknown')
                        logger.error(f"         [{j}] {tool_name} (ID: {tool_id})")
                        
                        # 查找对应的ToolMessage
                        found_response = False
                        for k in range(i + 1, len(messages)):
                            if (isinstance(messages[k], ToolMessage) and 
                                messages[k].tool_call_id == tool_id):
                                found_response = True
                                break
                            elif isinstance(messages[k], (HumanMessage, AIMessage)):
                                # 遇到新的对话轮次，停止查找
                                break
                        
                        if not found_response:
                            diagnosis["incomplete_tool_calls"].append({
                                "message_index": i,
                                "tool_name": tool_name,
                                "tool_id": tool_id,
                                "ai_message_content": msg.content
                            })
                            logger.error(f"         ❌ 未找到对应的ToolMessage!")
                        else:
                            logger.error(f"         ✅ 找到对应的ToolMessage")
            
            elif isinstance(msg, ToolMessage):
                logger.error(f"   [{i}] {msg_type}: {msg.name} (ID: {msg.tool_call_id})")
                
                # 检查是否有对应的AIMessage
                found_ai_message = False
                for k in range(i - 1, -1, -1):
                    if (isinstance(messages[k], AIMessage) and 
                        hasattr(messages[k], 'tool_calls') and 
                        messages[k].tool_calls):
                        if any(tc.get('id') == msg.tool_call_id for tc in messages[k].tool_calls):
                            found_ai_message = True
                            break
                    elif isinstance(messages[k], HumanMessage):
                        break
                
                if not found_ai_message:
                    diagnosis["orphaned_tool_messages"].append({
                        "message_index": i,
                        "tool_name": msg.name,
                        "tool_call_id": msg.tool_call_id
                    })
                    logger.error(f"       ❌ 未找到对应的AIMessage!")
            
            elif isinstance(msg, HumanMessage):
                logger.error(f"   [{i}] {msg_type}: '{msg.content[:50]}...'")
        
        # 生成修复建议
        if diagnosis["incomplete_tool_calls"]:
            logger.error(f"🔧 发现 {len(diagnosis['incomplete_tool_calls'])} 个不完整的工具调用")
            diagnosis["recommended_action"] = "fix_incomplete_tool_calls"
        elif diagnosis["orphaned_tool_messages"]:
            logger.error(f"🔧 发现 {len(diagnosis['orphaned_tool_messages'])} 个孤立的工具消息")
            diagnosis["recommended_action"] = "remove_orphaned_tool_messages"
        else:
            logger.error("🔧 未发现明显的消息格式问题")
            diagnosis["recommended_action"] = "unknown"
        
        return diagnosis

    def _fix_by_adding_missing_tool_messages(self, messages: List[BaseMessage], diagnosis: Dict) -> List[BaseMessage]:
        """
        通过添加缺失的ToolMessage来修复消息历史
        """
        logger.info("🔧 策略1: 补充缺失的ToolMessage")
        
        fixed_messages = list(messages)
        
        for incomplete in diagnosis["incomplete_tool_calls"]:
            # 为缺失的工具调用添加错误响应
            error_tool_message = ToolMessage(
                content="工具调用已超时或失败，请重新尝试。",
                tool_call_id=incomplete["tool_id"],
                name=incomplete["tool_name"]
            )
            
            # 插入到合适的位置
            insert_index = incomplete["message_index"] + 1
            fixed_messages.insert(insert_index, error_tool_message)
            
            logger.info(f"   ✅ 为工具调用 {incomplete['tool_name']}({incomplete['tool_id']}) 添加错误响应")
        
        return fixed_messages

    def _fix_by_removing_incomplete_tool_calls(self, messages: List[BaseMessage], diagnosis: Dict) -> List[BaseMessage]:
        """
        通过删除不完整的工具调用来修复消息历史
        """
        logger.info("🔧 策略2: 删除不完整的工具调用")
        
        fixed_messages = []
        
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 检查这个消息是否有不完整的工具调用
                has_incomplete = any(
                    inc["message_index"] == i 
                    for inc in diagnosis["incomplete_tool_calls"]
                )
                
                if has_incomplete:
                    # 如果有文本内容，保留文本内容但删除工具调用
                    if msg.content and msg.content.strip():
                        logger.info(f"   🔧 保留文本内容，删除工具调用: '{msg.content[:50]}...'")
                        fixed_msg = AIMessage(content=msg.content)
                        fixed_messages.append(fixed_msg)
                    else:
                        # 如果没有文本内容，创建一个说明性的消息
                        logger.info(f"   🔧 创建说明性消息替换空的工具调用")
                        fixed_msg = AIMessage(content="我需要重新分析这个问题。")
                        fixed_messages.append(fixed_msg)
                else:
                    fixed_messages.append(msg)
            else:
                fixed_messages.append(msg)
        
        return fixed_messages

    def _fix_by_rebuilding_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        重建消息历史，只保留完整的对话轮次
        """
        logger.info("🔧 策略3: 重建消息历史")
        
        clean_messages = []
        current_conversation = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                # 新的对话轮次开始
                if current_conversation:
                    # 检查上一轮对话是否完整
                    if self._is_conversation_complete(current_conversation):
                        clean_messages.extend(current_conversation)
                        logger.info(f"   ✅ 保留完整的对话轮次 ({len(current_conversation)} 条消息)")
                    else:
                        logger.info(f"   ❌ 跳过不完整的对话轮次 ({len(current_conversation)} 条消息)")
                
                current_conversation = [msg]
            else:
                current_conversation.append(msg)
        
        # 处理最后一轮对话
        if current_conversation:
            if self._is_conversation_complete(current_conversation):
                clean_messages.extend(current_conversation)
            else:
                # 最后一轮对话不完整，只保留用户消息
                clean_messages.extend([msg for msg in current_conversation if isinstance(msg, HumanMessage)])
        
        logger.info(f"   📊 重建完成: {len(messages)} -> {len(clean_messages)} 条消息")
        return clean_messages

    def _is_conversation_complete(self, conversation: List[BaseMessage]) -> bool:
        """
        检查对话轮次是否完整
        """
        for msg in conversation:
            if (isinstance(msg, AIMessage) and 
                hasattr(msg, 'tool_calls') and 
                msg.tool_calls):
                # 检查是否有对应的ToolMessage
                tool_call_ids = [tc.get('id') for tc in msg.tool_calls]
                found_responses = sum(
                    1 for m in conversation
                    if isinstance(m, ToolMessage) and m.tool_call_id in tool_call_ids
                )
                if found_responses < len(tool_call_ids):
                    return False
        return True

    async def _handle_parameter_error_with_retry(self, messages: List[BaseMessage], error_msg: str, attempt: int) -> List[BaseMessage]:
        """
        处理参数错误的完整流程
        """
        logger.error(f"🔧 处理参数错误 (重试 {attempt + 1}/3)")
        
        # 1. 诊断问题
        diagnosis = self._diagnose_parameter_error(messages, error_msg)
        
        # 2. 根据重试次数选择修复策略
        if attempt == 0:
            # 第一次重试：补充缺失的ToolMessage
            fixed_messages = self._fix_by_adding_missing_tool_messages(messages, diagnosis)
        elif attempt == 1:
            # 第二次重试：删除不完整的工具调用
            fixed_messages = self._fix_by_removing_incomplete_tool_calls(messages, diagnosis)
        else:
            # 第三次重试：重建消息历史
            fixed_messages = self._fix_by_rebuilding_history(messages)
        
        logger.info(f"🔧 修复完成: {len(messages)} -> {len(fixed_messages)} 条消息")
        return fixed_messages

    def _generate_contextual_fallback(self, messages: List[BaseMessage], diagnosis: Dict) -> str:
        """
        基于上下文生成合理的回答
        """
        # 分析用户的最新问题
        last_human_message = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                break
        
        if not last_human_message:
            return "抱歉，我无法理解您的问题。"
        
        # 分析是否是数据库相关问题
        question = last_human_message.content.lower()
        if any(keyword in question for keyword in ['查询', '数据', '服务区', '收入', '车流量']):
            return f"抱歉，在处理您关于「{last_human_message.content}」的查询时遇到了技术问题。请稍后重试，或者重新描述您的问题。"
        else:
            return "抱歉，我现在无法正确处理您的问题。请稍后重试或重新表述您的问题。"