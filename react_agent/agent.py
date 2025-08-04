"""
基于 StateGraph 的、具备上下文感知能力的 React Agent 核心实现
"""
import json
import pandas as pd
import httpx
import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from contextlib import AsyncExitStack

# 添加项目根目录到sys.path以解决模块导入问题
try:
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
except Exception as e:
    pass  # 忽略路径添加错误

# 使用统一日志系统
try:
    # 尝试相对导入（当作为模块导入时）
    from core.logging import get_react_agent_logger
except ImportError:
    # 如果相对导入失败，尝试绝对导入（直接运行时）
    from core.logging import get_react_agent_logger

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

logger = get_react_agent_logger("CustomReactAgent")

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
            streaming=True,
            extra_body={
                "enable_thinking": True,  # False by wxq
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
        logger.info(f"   ReactAgent LLM 已初始化，模型: {config.QWEN_MODEL}")

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
        
        # 6. 显示消息裁剪配置状态
        if config.MESSAGE_TRIM_ENABLED:
            logger.info(f"   消息裁剪已启用: 保留消息数={config.MESSAGE_TRIM_COUNT}, 搜索限制={config.MESSAGE_TRIM_SEARCH_LIMIT}")
        else:
            logger.info("   消息裁剪已禁用")
        
        logger.info("✅ CustomReactAgent 初始化完成。")

    async def _reinitialize_checkpointer(self):
        """重新初始化checkpointer连接"""
        try:
            # 清理旧的连接
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except:
                    pass
                
            # 重新创建
            if config.REDIS_ENABLED and AsyncRedisSaver is not None:
                self._exit_stack = AsyncExitStack()
                checkpointer_manager = AsyncRedisSaver.from_conn_string(config.REDIS_URL)
                self.checkpointer = await self._exit_stack.enter_async_context(checkpointer_manager)
                await self.checkpointer.asetup()
                logger.info("✅ Checkpointer重新初始化成功")
            else:
                self.checkpointer = None
                logger.warning("⚠️ Redis禁用，checkpointer设为None")
                
        except Exception as e:
            logger.error(f"❌ Checkpointer重新初始化失败: {e}")
            self.checkpointer = None

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

    def _trim_messages_node(self, state: AgentState) -> AgentState:
        """
        消息裁剪节点：确保从HumanMessage开始的完整对话轮次
        
        裁剪逻辑：
        1. 如果消息数 <= MESSAGE_TRIM_COUNT，不裁剪
        2. 取最近 MESSAGE_TRIM_COUNT 条消息
        3. 检查第一条是否为HumanMessage
        4. 如果不是，向前搜索最多 MESSAGE_TRIM_SEARCH_LIMIT 条消息找HumanMessage
        5. 如果找到，从HumanMessage开始保留；如果没找到，从原目标位置开始并记录WARNING
        """
        messages = state.get("messages", [])
        thread_id = state.get("thread_id", "unknown")
        original_count = len(messages)
        
        # 1. 检查是否需要裁剪
        if original_count <= config.MESSAGE_TRIM_COUNT:
            logger.info(f"[{thread_id}] 消息数量 {original_count} <= {config.MESSAGE_TRIM_COUNT}，无需裁剪")
            return state
        
        # 2. 开始裁剪逻辑
        target_count = config.MESSAGE_TRIM_COUNT
        search_limit = config.MESSAGE_TRIM_SEARCH_LIMIT
        
        # 3. 取最近的target_count条消息
        recent_start_index = original_count - target_count
        recent_messages = messages[-target_count:]
        first_msg = recent_messages[0]
        
        if config.DEBUG_MODE:
            logger.info(f"[{thread_id}] 开始消息裁剪分析:")
            logger.info(f"   原始消息数: {original_count}")
            logger.info(f"   目标保留数: {target_count}")
            logger.info(f"   初始截取索引: {recent_start_index}")
            logger.info(f"   第一条消息类型: {first_msg.type}")
        
        final_start_index = recent_start_index
        
        # 4. 检查第一条是否为HumanMessage
        if first_msg.type != "human":
            if config.DEBUG_MODE:
                logger.info(f"   第一条不是HumanMessage，开始向前搜索...")
            
            # 5. 向前搜索HumanMessage
            found_human = False
            search_start = recent_start_index - 1
            search_end = max(0, recent_start_index - search_limit)
            
            for i in range(search_start, search_end - 1, -1):
                if i >= 0 and messages[i].type == "human":
                    final_start_index = i
                    found_human = True
                    if config.DEBUG_MODE:
                        logger.info(f"   在索引 {i} 找到HumanMessage，向前扩展 {recent_start_index - i} 条")
                    break
            
            # 6. 如果没找到HumanMessage，记录WARNING
            if not found_human:
                logger.warning(f"[{thread_id}] 在向前 {search_limit} 条消息中未找到HumanMessage，从原目标位置 {recent_start_index} 开始截断")
                final_start_index = recent_start_index
        else:
            if config.DEBUG_MODE:
                logger.info(f"   第一条就是HumanMessage，无需向前搜索")
        
        # 7. 执行裁剪
        final_messages = messages[final_start_index:]
        final_count = len(final_messages)
        
        # 8. 记录裁剪结果
        logger.info(f"[{thread_id}] 消息裁剪完成: {original_count} → {final_count} 条 (从索引 {final_start_index} 开始)")
        
        if config.DEBUG_MODE:
            logger.info(f"   裁剪详情:")
            logger.info(f"     删除消息数: {original_count - final_count}")
            logger.info(f"     保留消息范围: [{final_start_index}:{original_count}]")
            
            # 显示前几条和后几条消息类型
            if final_count > 0:
                first_few = min(3, final_count)
                last_few = min(3, final_count)
                logger.info(f"     前{first_few}条类型: {[msg.type for msg in final_messages[:first_few]]}")
                if final_count > 3:
                    logger.info(f"     后{last_few}条类型: {[msg.type for msg in final_messages[-last_few:]]}")
        
        return {**state, "messages": final_messages}

    def _create_graph(self):
        """定义并编译最终的、正确的 StateGraph 结构。"""
        builder = StateGraph(AgentState)

        # 添加消息裁剪节点（如果启用）
        if config.MESSAGE_TRIM_ENABLED:
            builder.add_node("trim_messages", self._trim_messages_node)
        
        # 定义所有需要的节点 - 全部改为异步
        builder.add_node("agent", self._async_agent_node)
        builder.add_node("prepare_tool_input", self._async_prepare_tool_input_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("update_state_after_tool", self._async_update_state_after_tool_node)
        builder.add_node("format_final_response", self._async_format_final_response_node)

        # 建立正确的边连接
        if config.MESSAGE_TRIM_ENABLED:
            # 启用裁剪：START → trim_messages → agent
            builder.set_entry_point("trim_messages")
            builder.add_edge("trim_messages", "agent")
            logger.info("   ✅ 消息裁剪节点已启用，工作流: START → trim_messages → agent")
        else:
            # 禁用裁剪：START → agent
            builder.set_entry_point("agent")
            logger.info("   ⚠️ 消息裁剪节点已禁用，工作流: START → agent")
        
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
        thread_id = state.get("thread_id", "unknown")
        messages = state["messages"]
        total_messages = len(messages)
        
        # 显示当前递归计数
        current_count = getattr(self, '_recursion_count', 0)
        
        logger.info(f"🔄 [Decision] _async_should_continue - Thread: {thread_id} | 递归计数: {current_count}/{config.RECURSION_LIMIT}")
        logger.info(f"   消息总数: {total_messages}")
        
        if not messages:
            logger.warning("   ⚠️ 消息列表为空，返回 'end'")
            return "end"
        
        last_message = messages[-1]
        message_type = type(last_message).__name__
        
        logger.info(f"   最后消息类型: {message_type}")
        
        # 检查是否有tool_calls
        has_tool_calls = hasattr(last_message, "tool_calls") and last_message.tool_calls
        
        if has_tool_calls:
            tool_calls_count = len(last_message.tool_calls)
            logger.info(f"   发现工具调用: {tool_calls_count} 个")
            
            # 详细记录每个工具调用
            for i, tool_call in enumerate(last_message.tool_calls):
                tool_name = tool_call.get('name', 'unknown')
                tool_id = tool_call.get('id', 'unknown')
                logger.info(f"     工具调用[{i}]: {tool_name} (ID: {tool_id})")
            
            logger.info("   🔄 决策: continue (继续工具调用)")
            return "continue"
        else:
            logger.info("   ✅ 无工具调用")
            
            # 检查消息内容以了解为什么结束
            if hasattr(last_message, 'content'):
                content_preview = str(last_message.content)[:100] + "..." if len(str(last_message.content)) > 100 else str(last_message.content)
                logger.info(f"   消息内容预览: {content_preview}")
            
            logger.info("   🏁 决策: end (结束对话)")
            return "end"

    async def _async_agent_node(self, state: AgentState) -> Dict[str, Any]:
        """异步Agent 节点：使用异步LLM调用。"""
        # 增加递归计数
        if hasattr(self, '_recursion_count'):
            self._recursion_count += 1
        else:
            self._recursion_count = 1
            
        logger.info(f"🧠 [Async Node] agent - Thread: {state['thread_id']} | 递归计数: {self._recursion_count}/{config.RECURSION_LIMIT}")
        
        # 获取建议的下一步操作
        next_step = state.get("suggested_next_step")
        
        # 构建发送给LLM的消息列表
        messages_for_llm = state["messages"].copy()
        
        # 🎯 添加数据库范围系统提示词（每次用户提问时添加）
        if isinstance(state["messages"][-1], HumanMessage):
            db_scope_prompt = self._get_database_scope_prompt()
            if db_scope_prompt:
                messages_for_llm.insert(0, SystemMessage(content=db_scope_prompt))
                logger.info("   ✅ 已添加数据库范围判断提示词")
        
        # 检查是否需要分析验证错误
        
        # 行为指令与工具建议分离
        real_tools = {'valid_sql', 'run_sql'}
        
        if next_step:
            if next_step in real_tools:
                # 场景1: 建议调用一个真实的工具
                instruction = f"Suggestion: Based on the previous step, please use the '{next_step}' tool to continue."
                messages_for_llm.append(SystemMessage(content=instruction))
                logger.info(f"   ✅ 已添加工具建议: {next_step}")

            elif next_step == "analyze_validation_error":
                # 场景2: 分析SQL验证错误（特殊指令）
                for msg in reversed(state["messages"]):
                    if isinstance(msg, ToolMessage) and msg.name == "valid_sql":
                        error_guidance = self._generate_validation_error_guidance(msg.content)
                        messages_for_llm.append(SystemMessage(content=error_guidance))
                        logger.info("   ✅ 已添加SQL验证错误指导")
                        break
            
            elif next_step == 'summarize_final_answer':
                # 场景3: 总结最终答案（行为指令）
                instruction = "System Instruction: The SQL query was executed successfully. Please analyze the JSON data in the last message and summarize it in natural, user-friendly language as the final answer. Do not expose the raw JSON data or SQL statements in your response."
                messages_for_llm.append(SystemMessage(content=instruction))
                logger.info("   ✅ 已添加 '总结答案' 行为指令")

            elif next_step == 'answer_with_common_sense':
                # 场景4: 基于常识回答（特殊指令）
                instruction = (
                    "无法为当前问题生成有效的SQL查询。失败原因已在上下文中提供。"
                    "请你直接利用自身的知识库来回答用户的问题，不要再重复解释失败的原因。"
                )
                messages_for_llm.append(SystemMessage(content=instruction))
                logger.info("✅ 已添加 '常识回答' 行为指令")

        # 🛡️ 添加防幻觉系统提示词（重点防止参数篡改）
        anti_hallucination_prompt = self._get_anti_hallucination_prompt(state)
        if anti_hallucination_prompt:
            messages_for_llm.append(SystemMessage(content=anti_hallucination_prompt))
            logger.info("   🛡️ 已添加防幻觉系统提示词")

        # 🔍 【新增】详细日志：发送给LLM的完整消息列表（按实际提交顺序）
        logger.info("📤 发送给LLM的完整消息列表和参数:")
        logger.info(f"   总消息数: {len(messages_for_llm)}")
        logger.info("   消息详情:")
        for i, msg in enumerate(messages_for_llm):
            msg_type = type(msg).__name__
            content = str(msg.content)
            
            # 对于长内容，显示前500字符并标记
            if len(content) > 500:
                content_display = content[:500] + f"... (内容被截断，完整长度: {len(content)}字符)"
            else:
                content_display = content
                
            logger.info(f"   [{i}] {msg_type}:")
            # 多行显示内容，便于阅读
            for line in content_display.split('\n'):
                logger.info(f"      {line}")

        # 添加重试机制处理网络连接问题
        import asyncio
        max_retries = config.MAX_RETRIES
        for attempt in range(max_retries):
            try:
                # 🔍 【调试】打印LLM调用的详细信息
                logger.info(f"🚀 准备调用LLM (尝试 {attempt + 1}/{max_retries})")
                logger.info(f"   LLM实例: {type(self.llm_with_tools)}")
                logger.info(f"   消息数量: {len(messages_for_llm)}")
                
                # 🔍 【调试】检查消息格式是否正确
                for i, msg in enumerate(messages_for_llm):
                    logger.debug(f"   消息[{i}] 类型: {type(msg)}")
                    logger.debug(f"   消息[{i}] 有content: {hasattr(msg, 'content')}")
                    if hasattr(msg, 'content'):
                        logger.debug(f"   消息[{i}] content类型: {type(msg.content)}")
                        logger.debug(f"   消息[{i}] content长度: {len(str(msg.content))}")
                
                # 使用异步调用
                logger.info("🔄 开始调用LLM...")
                response = await self.llm_with_tools.ainvoke(messages_for_llm)
                logger.info("✅ LLM调用完成")
                
                # 🔍 【调试】详细的响应检查和日志
                logger.info(f"   响应类型: {type(response)}")
                logger.info(f"   响应有content: {hasattr(response, 'content')}")
                logger.info(f"   响应有tool_calls: {hasattr(response, 'tool_calls')}")
                logger.info(f"   LLM原始响应内容: '{response.content}'")
                logger.info(f"   响应内容长度: {len(response.content) if response.content else 0}")
                logger.info(f"   响应内容类型: {type(response.content)}")
                if hasattr(response, 'tool_calls'):
                    logger.info(f"   LLM是否有工具调用: {response.tool_calls}")
                else:
                    logger.info(f"   LLM是否有工具调用: 无tool_calls属性")

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
        """异步准备工具输入节点：为generate_sql工具注入history_messages。"""
        # 增加递归计数
        if hasattr(self, '_recursion_count'):
            self._recursion_count += 1
        else:
            self._recursion_count = 1
            
        logger.info(f"🔧 [Async Node] prepare_tool_input - Thread: {state['thread_id']} | 递归计数: {self._recursion_count}/{config.RECURSION_LIMIT}")
        
        # 获取最后一条消息（应该是来自agent的AIMessage）
        last_message = state["messages"][-1]

        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": [last_message]}

        # 强制修正LLM幻觉出的问题
        for tool_call in last_message.tool_calls:
            if tool_call['name'] == 'generate_sql':
                original_user_question = next((msg.content for msg in reversed(state['messages']) if isinstance(msg, HumanMessage)), None)
                if original_user_question and tool_call['args'].get('question') != original_user_question:
                    logger.warning(
                        f"修正 'generate_sql' 的问题参数。\n"
                        f"  - LLM提供: '{tool_call['args'].get('question')}'\n"
                        f"  + 修正为: '{original_user_question}'"
                    )
                    tool_call['args']['question'] = original_user_question

        # 恢复原始的、更健壮的历史消息过滤和注入逻辑
        new_tool_calls = []
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "generate_sql":
                logger.info("检测到 generate_sql 调用，开始注入历史消息。")
                modified_args = tool_call["args"].copy()
                
                clean_history = []
                
                # 找到当前用户问题，确保不包含在历史上下文中
                current_user_question = None
                messages_for_history = []
                
                # 从最后开始找到当前用户问题
                for i in range(len(state["messages"]) - 1, -1, -1):
                    msg = state["messages"][i]
                    if isinstance(msg, HumanMessage):
                        current_user_question = msg.content
                        messages_for_history = state["messages"][:i]  # 排除当前用户问题及之后的消息
                        break
                
                # 处理历史消息，确保不包含当前用户问题
                for msg in messages_for_history:
                    if isinstance(msg, HumanMessage):
                        clean_history.append({"type": "human", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        if not msg.tool_calls and msg.content:
                            # 注释掉 [Formatted Output] 清理逻辑 - 源头已不生成前缀
                            # clean_content = msg.content.replace("[Formatted Output]\n", "").strip()
                            clean_content = msg.content.strip()
                            if clean_content:
                                clean_history.append({"type": "ai", "content": clean_content})
                
                modified_args["history_messages"] = clean_history
                logger.info(f"注入了 {len(clean_history)} 条过滤后的历史消息")
                
                new_tool_calls.append({
                    "name": tool_call["name"],
                    "args": modified_args,
                    "id": tool_call["id"],
                })
            else:
                new_tool_calls.append(tool_call)
        
        last_message.tool_calls = new_tool_calls
        return {"messages": [last_message]}

    def _filter_and_format_history(self, messages: list) -> list:
        """
        过滤和格式化历史消息，为generate_sql工具提供干净的上下文。
        只保留历史中的用户提问和AI的最终回答。
        """
        clean_history = []
        # 处理除最后一个（即当前的工具调用）之外的所有消息
        messages_to_process = messages[:-1]

        for msg in messages_to_process:
            if isinstance(msg, HumanMessage):
                clean_history.append({"type": "human", "content": msg.content})
            elif isinstance(msg, AIMessage):
                # 只保留最终的、面向用户的回答（不包含工具调用的纯文本回答）
                if not msg.tool_calls and msg.content:
                    # 注释掉 [Formatted Output] 清理逻辑 - 源头已不生成前缀
                    # clean_content = msg.content.replace("[Formatted Output]\n", "").strip()
                    clean_content = msg.content.strip()
                    if clean_content:
                        clean_history.append({"type": "ai", "content": clean_content})
        
        return clean_history

    async def _async_update_state_after_tool_node(self, state: AgentState) -> Dict[str, Any]:
        """异步更新工具执行后的状态。"""
        # 增加递归计数
        if hasattr(self, '_recursion_count'):
            self._recursion_count += 1
        else:
            self._recursion_count = 1
            
        logger.info(f"📝 [Async Node] update_state_after_tool - Thread: {state['thread_id']} | 递归计数: {self._recursion_count}/{config.RECURSION_LIMIT}")
        
        # 获取最后一条工具消息
        last_message = state["messages"][-1]
        tool_name = last_message.name
        tool_output = last_message.content
        next_step = None

        if tool_name == 'generate_sql':
            # 使用 .lower() 将输出转为小写，可以同时捕获 "failed" 和 "Failed" 等情况
            tool_output_lower = tool_output.lower()
            if "failed" in tool_output_lower or "无法生成" in tool_output_lower or "失败" in tool_output_lower:
                next_step = 'answer_with_common_sense'
            else:
                next_step = 'valid_sql'
        
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
        """异步格式化最终响应节点。"""
        # 增加递归计数
        if hasattr(self, '_recursion_count'):
            self._recursion_count += 1
        else:
            self._recursion_count = 1
            
        logger.info(f"✨ [Async Node] format_final_response - Thread: {state['thread_id']} | 递归计数: {self._recursion_count}/{config.RECURSION_LIMIT}")
        
        # 这个节点主要用于最终处理，通常不需要修改状态
        return {"messages": state["messages"]}

    async def _async_generate_api_data(self, state: AgentState) -> Dict[str, Any]:
        """异步生成API格式的数据结构"""
        logger.info("📊 异步生成API格式数据...")
        
        last_message = state['messages'][-1]
        response_content = last_message.content
        
        # 注释掉 [Formatted Output] 清理逻辑 - 源头已不生成前缀
        # if response_content.startswith("[Formatted Output]\n"):
        #     response_content = response_content.replace("[Formatted Output]\n", "")
        
        api_data = {
            "response": response_content
        }

        # --- 新增逻辑：为 answer_with_common_sense 场景拼接响应 ---
        if state.get("suggested_next_step") == 'answer_with_common_sense':
            failure_reason = self._find_generate_sql_failure_reason(state['messages'])
            if failure_reason:
                # 将 "Database query failed. Reason: " 前缀移除，使其更自然
                cleaned_reason = failure_reason.replace("Database query failed. Reason:", "").strip()
                # 拼接失败原因和LLM的常识回答
                api_data["response"] = f"{cleaned_reason}\n\n{response_content}"
                logger.info("   ✅ 已成功拼接 '失败原因' 和 '常识回答'")
        
        sql_info = await self._async_extract_sql_and_data(state['messages'])
        if sql_info['sql']:
            api_data["sql"] = sql_info['sql']
        if sql_info['records']:
            api_data["records"] = sql_info['records']
        
        # 生成Agent元数据
        api_data["react_agent_meta"] = await self._async_collect_agent_metadata(state)
        
        logger.info(f"   API数据生成完成，包含字段: {list(api_data.keys())}")
        return api_data

    def _find_generate_sql_failure_reason(self, messages: List[BaseMessage]) -> Optional[str]:
        """从后向前查找最近一次generate_sql失败的原因"""
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == 'generate_sql':
                # 找到最近的generate_sql工具消息
                if "failed" in msg.content.lower() or "失败" in msg.content.lower():
                    return msg.content
                else:
                    # 如果是成功的消息，说明当前轮次没有失败，停止查找
                    return None
        return None

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
        
        # 初始化递归计数器（用于日志显示）
        self._recursion_count = 0
        
        run_config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "recursion_limit": config.RECURSION_LIMIT
        }
        
        logger.info(f"🔢 递归限制设置: {config.RECURSION_LIMIT}")
        
        inputs = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "thread_id": thread_id,
            "suggested_next_step": None,
        }

        try:
            logger.info(f"🚀 开始处理用户消息: {message[:50]}...")
            
            # 检查checkpointer状态，如果Redis连接有问题则重新初始化
            if self.checkpointer:
                try:
                    # 简单的连接测试 - 不用aget_tuple因为可能没有数据
                    # 直接测试Redis连接
                    if hasattr(self.checkpointer, 'conn') and self.checkpointer.conn:
                        await self.checkpointer.conn.ping()
                except Exception as checkpoint_error:
                    if "Event loop is closed" in str(checkpoint_error) or "closed" in str(checkpoint_error).lower():
                        logger.warning(f"⚠️ Checkpointer连接异常，尝试重新初始化: {checkpoint_error}")
                        await self._reinitialize_checkpointer()
                        # 重新构建graph使用新的checkpointer
                        self.agent_executor = self._create_graph()
                    else:
                        logger.warning(f"⚠️ Checkpointer测试失败，但继续执行: {checkpoint_error}")
            
            final_state = await self.agent_executor.ainvoke(inputs, run_config)
            
            # 🔍 调试：打印 final_state 的所有 keys
            logger.info(f"🔍 Final state keys: {list(final_state.keys())}")
            
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
            
            # 生成API格式数据
            api_data = await self._async_generate_api_data(final_state)
            result["api_data"] = api_data
            logger.info("   🔌 已生成API格式数据")
            
            return result
            
        except Exception as e:
            # 特殊处理Redis相关的Event loop错误
            if "Event loop is closed" in str(e):
                logger.error(f"❌ Redis Event loop已关闭 - Thread: {thread_id}: {e}")
                # 尝试重新初始化checkpointer
                try:
                    await self._reinitialize_checkpointer()
                    self.agent_executor = self._create_graph()
                    logger.info("🔄 已重新初始化checkpointer，请重试请求")
                except Exception as reinit_error:
                    logger.error(f"❌ 重新初始化失败: {reinit_error}")
                
                return {
                    "success": False, 
                    "error": "Redis连接问题，请重试", 
                    "thread_id": thread_id,
                    "retry_suggested": True
                }
            else:
                logger.error(f"❌ 处理过程中发生严重错误 - Thread: {thread_id}: {e}", exc_info=True)
                return {"success": False, "error": str(e), "thread_id": thread_id}
    
    async def get_conversation_history(self, thread_id: str, include_tools: bool = False) -> Dict[str, Any]:
        """
        从 checkpointer 获取指定线程的对话历史，支持消息过滤和时间戳。
        
        Args:
            thread_id: 线程ID
            include_tools: 是否包含工具消息，默认False（只返回human和ai消息）
            
        Returns:
            Dict包含: {
                "messages": List[Dict],  # 消息列表
                "thread_created_at": str,  # 线程创建时间
                "total_checkpoints": int   # 总checkpoint数
            }
        """
        if not self.checkpointer:
            return {"messages": [], "thread_created_at": None, "total_checkpoints": 0}
        
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # 获取所有历史checkpoint，按时间倒序
            checkpoints = []
            async for checkpoint_tuple in self.checkpointer.alist(thread_config):
                checkpoints.append(checkpoint_tuple)
            
            if not checkpoints:
                return {"messages": [], "thread_created_at": None, "total_checkpoints": 0}
            
            # 解析thread_id中的创建时间
            thread_created_at = self._parse_thread_creation_time(thread_id)
            
            # 构建消息到时间戳的映射
            message_timestamps = self._build_message_timestamp_map(checkpoints)
            
            # 获取最新状态的消息
            latest_checkpoint = checkpoints[0]
            messages = latest_checkpoint.checkpoint.get('channel_values', {}).get('messages', [])
            
            # 过滤和格式化消息
            filtered_messages = []
            for msg in messages:
                # 确定消息类型
                if isinstance(msg, HumanMessage):
                    msg_type = "human"
                elif isinstance(msg, ToolMessage):
                    if not include_tools:
                        continue  # 跳过工具消息
                    msg_type = "tool"
                else:  # AIMessage
                    msg_type = "ai"
                    # 如果不包含工具消息，跳过只有工具调用没有内容的AI消息
                    if not include_tools and (not msg.content and hasattr(msg, 'tool_calls') and msg.tool_calls):
                        continue
                
                # 获取消息ID
                msg_id = getattr(msg, 'id', None)
                if not msg_id:
                    continue  # 跳过没有ID的消息
                
                # 获取时间戳
                timestamp = message_timestamps.get(msg_id)
                if not timestamp:
                    # 如果没有找到精确时间戳，使用最新checkpoint的时间
                    timestamp = latest_checkpoint.checkpoint.get('ts')
                
                filtered_messages.append({
                    "id": msg_id,
                    "type": msg_type,
                    "content": msg.content,
                    "timestamp": timestamp
                })
            
            return {
                "messages": filtered_messages,
                "thread_created_at": thread_created_at,
                "total_checkpoints": len(checkpoints)
            }
            
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"⚠️ Event loop已关闭，尝试重新获取对话历史: {thread_id}")
                return {"messages": [], "thread_created_at": None, "total_checkpoints": 0}
            else:
                raise
        except Exception as e:
            logger.error(f"❌ 获取对话历史失败: {e}")
            return {"messages": [], "thread_created_at": None, "total_checkpoints": 0}
    
    def _parse_thread_creation_time(self, thread_id: str) -> str:
        """解析thread_id中的创建时间，返回带毫秒的格式"""
        try:
            if ':' in thread_id:
                parts = thread_id.split(':')
                if len(parts) >= 2:
                    timestamp_part = parts[1]
                    if len(timestamp_part) >= 14:
                        year = timestamp_part[:4]
                        month = timestamp_part[4:6] 
                        day = timestamp_part[6:8]
                        hour = timestamp_part[8:10]
                        minute = timestamp_part[10:12]
                        second = timestamp_part[12:14]
                        ms = timestamp_part[14:17] if len(timestamp_part) > 14 else "000"
                        return f"{year}-{month}-{day} {hour}:{minute}:{second}.{ms}"
        except Exception as e:
            logger.warning(f"⚠️ 解析thread创建时间失败: {e}")
        return None
    
    def _build_message_timestamp_map(self, checkpoints: List) -> Dict[str, str]:
        """构建消息ID到时间戳的映射"""
        message_timestamps = {}
        
        # 按时间正序排列checkpoint（最早的在前）
        checkpoints_sorted = sorted(checkpoints, key=lambda x: x.checkpoint.get('ts', ''))
        
        for checkpoint_tuple in checkpoints_sorted:
            checkpoint_ts = checkpoint_tuple.checkpoint.get('ts')
            messages = checkpoint_tuple.checkpoint.get('channel_values', {}).get('messages', [])
            
            # 为这个checkpoint中的新消息分配时间戳
            for msg in messages:
                msg_id = getattr(msg, 'id', None)
                if msg_id and msg_id not in message_timestamps:
                    message_timestamps[msg_id] = checkpoint_ts
        
        return message_timestamps 

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
            
            # 注意：不要关闭共享的Redis客户端连接，因为其他操作可能还在使用
            # await redis_client.close()  # 已注释掉，避免关闭共享连接
            
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
                        
                        # 获取最后一条用户消息
                        last_human_message = None
                        if messages:
                            for msg in reversed(messages):
                                if isinstance(msg, HumanMessage):
                                    last_human_message = msg.content
                                    break
                        
                        conversations.append({
                            "conversation_id": thread_id,
                            "thread_id": thread_id,
                            "user_id": user_id,
                            "message_count": len(messages),
                            "last_message": last_human_message,
                            "updated_at": self._format_utc_to_china_time(state.get('ts')) if state.get('ts') else None,
                            "conversation_title": preview,
                            "created_at": self._format_timestamp(thread_info["timestamp"])
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
        """格式化时间戳为可读格式，包含毫秒"""
        try:
            # timestamp格式: 20250710123137984
            if len(timestamp) >= 14:
                year = timestamp[:4]
                month = timestamp[4:6]
                day = timestamp[6:8]
                hour = timestamp[8:10]
                minute = timestamp[10:12]
                second = timestamp[12:14]
                # 提取毫秒部分（如果存在）
                millisecond = timestamp[14:17] if len(timestamp) > 14 else "000"
                return f"{year}-{month}-{day} {hour}:{minute}:{second}.{millisecond}"
        except Exception:
            pass
        return timestamp
    
    def _format_utc_to_china_time(self, utc_time_str: str) -> str:
        """将UTC时间转换为中国时区时间格式"""
        try:
            from datetime import datetime, timezone, timedelta
            
            # 解析UTC时间字符串
            # 格式: "2025-07-17T13:21:52.868292+00:00"
            dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
            
            # 转换为中国时区 (UTC+8)
            china_tz = timezone(timedelta(hours=8))
            china_time = dt.astimezone(china_tz)
            
            # 格式化为目标格式: "2025-07-17 21:12:02.456"
            return china_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 只保留3位毫秒
        except Exception as e:
            logger.warning(f"时间格式转换失败: {e}")
            return utc_time_str 

    def _get_database_scope_prompt(self) -> str:
        """Get database scope prompt for intelligent query decision making"""
        try:
            import os
            # Read local db_query_decision_prompt.txt
            current_dir = os.path.dirname(os.path.abspath(__file__))
            db_scope_file = os.path.join(current_dir, "db_query_decision_prompt.txt")
            
            with open(db_scope_file, 'r', encoding='utf-8') as f:
                db_scope_content = f.read().strip()
            
            prompt = f"""You are an intelligent database query assistant. When deciding whether to use database query tools, please follow these rules:

=== DATABASE BUSINESS SCOPE ===
{db_scope_content}

=== DECISION RULES ===
1. If the question involves data within the above business scope (service areas, branches, revenue, traffic flow, etc.), use the generate_sql tool
2. If the question is about general knowledge (like "when do lychees ripen?", weather, historical events, etc.), answer directly based on your knowledge WITHOUT using database tools
3. When answering general knowledge questions, provide clear and helpful answers without any special prefixes

=== FALLBACK STRATEGY ===
When generate_sql returns an error message or when queries return no results:
1. First, check if the question is within the database scope described above
2. For questions clearly OUTSIDE the database scope (world events, general knowledge, etc.):
   - Provide the answer based on your knowledge immediately
   - Give a direct, natural answer without any prefixes or disclaimers
3. For questions within database scope but queries return no results:
   - If it's a reasonable question that might have a general answer, provide it naturally
4. For questions that definitely require specific database data:
   - Acknowledge the limitation and suggest the data may not be available
   - Do not attempt to guess or fabricate specific data

Please intelligently choose whether to query the database based on the nature of the user's question,
not on explaining your decision-making process.
"""
            
            return prompt
            
        except Exception as e:
            logger.warning(f"⚠️ Unable to read database scope description file: {e}")
            return ""

    def _generate_validation_error_guidance(self, validation_error: str) -> str:
        """根据验证错误类型生成具体的修复指导"""
        
        # 优先处理最常见的语法错误
        if "语法错误" in validation_error or "syntax error" in validation_error.lower():
            return """SQL验证失败：语法错误。
处理建议：
1. 仔细检查SQL语法（括号、引号、关键词等）
2. 修复语法错误后，调用 valid_sql 工具重新验证
3. 常见问题：缺少逗号、括号不匹配、关键词拼写错误"""

        # 新增的合并条件，处理所有"不存在"类型的错误
        elif ("不存在" in validation_error or 
              "no such table" in validation_error.lower() or
              "does not exist" in validation_error.lower()):
            return """SQL验证失败：表或字段不存在。
处理建议：
1. 请明确告知用户，因数据库缺少相应的表或字段，无法通过SQL查询获取准确答案。
2. 请基于你的通用知识和常识，直接回答用户的问题或提供相关解释。
3. 请不要再尝试生成或修复SQL。"""

        # 其他原有分支可以被新逻辑覆盖，故移除
        # Fallback 到通用的错误处理
        else:
            return f"""SQL验证失败：{validation_error}
处理建议：
1. 如果这是一个可以修复的错误，请尝试修正并再次验证。
2. 如果错误表明数据缺失，请直接向用户说明情况。
3. 避免猜测或编造数据库中不存在的信息。"""

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

    def _get_anti_hallucination_prompt(self, state: AgentState) -> str:
        """
        生成防幻觉提示词，专注于保持参数原样传递
        """
        # 获取当前用户的最新问题
        last_user_message = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_user_message = msg.content
                break
        
        if not last_user_message:
            return ""
        
        prompt = f"""🛡️ 关键指令：工具调用参数必须完全准确

用户当前问题：「{last_user_message}」

调用工具时的严格要求：
1. **原样传递原则**：question 参数必须与用户问题完全一致，一字不差
2. **禁止任何改写**：不得进行同义词替换、语言优化或任何形式的修改

❌ 错误示例：
- 用户问"充电桩"，不得改为"充电栋"
✅ 正确做法：
- 完全复制用户的原始问题作为question参数

请严格遵守此要求，确保工具调用的准确性。"""
        
        return prompt