"""
同步版本的React Agent - 解决Vector搜索异步冲突问题
基于原有CustomReactAgent，但使用完全同步的实现
"""
import json
import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import redis

# 添加项目根目录到sys.path
try:
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
except Exception as e:
    pass

from core.logging import get_react_agent_logger
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# 导入同步版本的依赖
try:
    from . import config
    from .state import AgentState
    from .sql_tools import sql_tools
except ImportError:
    import config
    from state import AgentState
    from sql_tools import sql_tools

logger = get_react_agent_logger("SyncCustomReactAgent")

class SyncCustomReactAgent:
    """
    同步版本的React Agent
    专门解决Vector搜索的异步事件循环冲突问题
    """
    
    def __init__(self):
        """私有构造函数，请使用 create() 类方法来创建实例。"""
        self.llm = None
        self.tools = None
        self.agent_executor = None
        self.checkpointer = None
        self.redis_client = None

    @classmethod
    def create(cls):
        """同步工厂方法，创建并初始化 SyncCustomReactAgent 实例。"""
        instance = cls()
        instance._sync_init()
        return instance

    def _sync_init(self):
        """同步初始化所有组件。"""
        logger.info("🚀 开始初始化 SyncCustomReactAgent...")

        # 1. 初始化同步Redis客户端（如果需要）
        try:
            self.redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            logger.info(f"   ✅ Redis连接成功: {config.REDIS_URL}")
        except Exception as e:
            logger.warning(f"   ⚠️ Redis连接失败，将不使用checkpointer: {e}")
            self.redis_client = None

        # 2. 初始化 LLM（同步版本）
        self.llm = ChatOpenAI(
            api_key=config.QWEN_API_KEY,
            base_url=config.QWEN_BASE_URL,
            model=config.QWEN_MODEL,
            temperature=0.1,
            timeout=config.NETWORK_TIMEOUT,
            max_retries=0,
            streaming=False,  # 关键：禁用流式处理
            extra_body={
                "enable_thinking": False,  # 明确设置为False：非流式调用必须设为false
                "misc": {
                    "ensure_ascii": False
                }
            }
        )
        logger.info(f"   ✅ 同步LLM已初始化，模型: {config.QWEN_MODEL}")

        # 3. 绑定工具
        self.tools = sql_tools
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        logger.info(f"   ✅ 已绑定 {len(self.tools)} 个工具")

        # 4. 创建StateGraph（不使用checkpointer避免异步依赖）
        self.agent_executor = self._create_sync_graph()
        logger.info("   ✅ 同步StateGraph已创建")

        logger.info("✅ SyncCustomReactAgent 初始化完成")

    def _create_sync_graph(self):
        """创建同步的StateGraph"""
        graph = StateGraph(AgentState)
        
        # 添加同步节点
        graph.add_node("agent", self._sync_agent_node)
        graph.add_node("tools", ToolNode(self.tools))
        graph.add_node("prepare_tool_input", self._sync_prepare_tool_input_node)
        graph.add_node("update_state_after_tool", self._sync_update_state_after_tool_node)
        graph.add_node("format_final_response", self._sync_format_final_response_node)

        # 设置入口点
        graph.set_entry_point("agent")

        # 添加条件边
        graph.add_conditional_edges(
            "agent",
            self._sync_should_continue,
            {
                "tools": "prepare_tool_input",
                "end": "format_final_response"
            }
        )

        # 添加普通边
        graph.add_edge("prepare_tool_input", "tools")
        graph.add_edge("tools", "update_state_after_tool")
        graph.add_edge("update_state_after_tool", "agent")
        graph.add_edge("format_final_response", END)

        # 关键：使用同步编译，不传入checkpointer
        return graph.compile()

    def _sync_agent_node(self, state: AgentState) -> Dict[str, Any]:
        """同步Agent节点"""
        logger.info(f"🧠 [Sync Node] agent - Thread: {state.get('thread_id', 'unknown')}")
        
        messages_for_llm = state["messages"].copy()
        
        # 添加数据库范围提示词
        if isinstance(state["messages"][-1], HumanMessage):
            db_scope_prompt = self._get_database_scope_prompt()
            if db_scope_prompt:
                messages_for_llm.insert(0, SystemMessage(content=db_scope_prompt))
                logger.info("   ✅ 已添加数据库范围判断提示词")

        # 同步LLM调用
        response = self.llm_with_tools.invoke(messages_for_llm)
        
        return {"messages": [response]}

    def _sync_should_continue(self, state: AgentState):
        """同步条件判断"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not last_message.tool_calls:
            return "end"
        else:
            return "tools"

    def _sync_prepare_tool_input_node(self, state: AgentState) -> Dict[str, Any]:
        """同步准备工具输入节点"""
        logger.info(f"🔧 [Sync Node] prepare_tool_input - Thread: {state.get('thread_id', 'unknown')}")
        
        last_message = state["messages"][-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                if tool_call.get('name') == 'generate_sql':
                    # 注入历史消息
                    history_messages = self._filter_and_format_history(state["messages"])
                    if 'args' not in tool_call:
                        tool_call['args'] = {}
                    tool_call['args']['history_messages'] = history_messages
                    logger.info(f"   ✅ 为generate_sql注入了 {len(history_messages)} 条历史消息")

        return {"messages": [last_message]}

    def _sync_update_state_after_tool_node(self, state: AgentState) -> Dict[str, Any]:
        """同步更新工具执行后的状态"""
        logger.info(f"📝 [Sync Node] update_state_after_tool - Thread: {state.get('thread_id', 'unknown')}")
        
        last_message = state["messages"][-1]
        tool_name = last_message.name
        tool_output = last_message.content
        next_step = None

        if tool_name == 'generate_sql':
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

    def _sync_format_final_response_node(self, state: AgentState) -> Dict[str, Any]:
        """同步格式化最终响应节点"""
        logger.info(f"📄 [Sync Node] format_final_response - Thread: {state.get('thread_id', 'unknown')}")
        
        messages = state["messages"]
        last_message = messages[-1]
        
        # 构建最终响应
        final_response = last_message.content
        
        logger.info(f"   ✅ 最终响应已准备完成")
        return {"final_answer": final_response}

    def _filter_and_format_history(self, messages: list) -> list:
        """过滤和格式化历史消息"""
        clean_history = []
        for msg in messages[:-1]:  # 排除最后一条消息
            if isinstance(msg, HumanMessage):
                clean_history.append({"type": "human", "content": msg.content})
            elif isinstance(msg, AIMessage):
                clean_content = msg.content if not hasattr(msg, 'tool_calls') or not msg.tool_calls else ""
                if clean_content.strip():
                    clean_history.append({"type": "ai", "content": clean_content})
        
        return clean_history

    def _get_database_scope_prompt(self) -> str:
        """获取数据库范围判断提示词"""
        return """你是一个专门处理高速公路收费数据查询的AI助手。在回答用户问题时，请首先判断这个问题是否可以通过查询数据库来回答。

数据库包含以下类型的数据：
- 服务区信息（名称、位置、档口数量等）
- 收费站数据
- 车流量统计
- 业务数据分析

如果用户的问题与这些数据相关，请使用工具生成SQL查询。
如果问题与数据库内容无关（如常识性问题、天气、新闻等），请直接用你的知识回答，不要尝试生成SQL。"""

    def chat(self, message: str, user_id: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        同步聊天方法 - 关键：使用 graph.invoke() 而不是 ainvoke()
        """
        if thread_id is None:
            import uuid
            thread_id = str(uuid.uuid4())

        # 构建输入
        inputs = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "thread_id": thread_id,
            "suggested_next_step": None
        }

        # 构建运行配置（不使用checkpointer）
        run_config = {
            "recursion_limit": config.RECURSION_LIMIT,
        }

        try:
            logger.info(f"🚀 开始同步处理用户消息: {message[:50]}...")
            
            # 关键：使用同步的 invoke() 方法
            final_state = self.agent_executor.invoke(inputs, run_config)
            
            logger.info(f"🔍 Final state keys: {list(final_state.keys())}")
            
            # 提取答案
            if final_state["messages"]:
                answer = final_state["messages"][-1].content
            else:
                answer = "抱歉，无法处理您的请求。"
            
            # 提取SQL数据（如果有）
            sql_data = self._extract_latest_sql_data(final_state["messages"])
            
            logger.info(f"✅ 同步处理完成 - Final Answer: '{answer[:100]}...'")
            
            # 构建返回结果
            result = {
                "success": True, 
                "answer": answer, 
                "thread_id": thread_id
            }
            
            # 只有当存在SQL数据时才添加到返回结果中
            if sql_data:
                try:
                    # 尝试解析SQL数据
                    sql_parsed = json.loads(sql_data)
                    
                    # 检查数据格式：run_sql工具返回的是数组格式 [{"col1":"val1"}]
                    if isinstance(sql_parsed, list):
                        # 数组格式：直接作为records使用
                        result["api_data"] = {
                            "response": answer,
                            "records": sql_parsed,
                            "react_agent_meta": {
                                "thread_id": thread_id,
                                "agent_version": "sync_react_v1"
                            }
                        }
                    elif isinstance(sql_parsed, dict):
                        # 字典格式：按原逻辑处理
                        result["api_data"] = {
                            "response": answer,
                            "sql": sql_parsed.get("sql", ""),
                            "records": sql_parsed.get("records", []),
                            "react_agent_meta": {
                                "thread_id": thread_id,
                                "agent_version": "sync_react_v1"
                            }
                        }
                    else:
                        logger.warning(f"SQL数据格式未知: {type(sql_parsed)}")
                        raise ValueError("Unknown SQL data format")
                        
                except (json.JSONDecodeError, AttributeError, ValueError) as e:
                    logger.warning(f"SQL数据格式处理失败: {str(e)}, 跳过API数据构建")
            else:
                result["api_data"] = {
                    "response": answer,
                    "react_agent_meta": {
                        "thread_id": thread_id,
                        "agent_version": "sync_react_v1"
                    }
                }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 同步处理失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"同步处理失败: {str(e)}",
                "thread_id": thread_id,
                "retry_suggested": True
            }

    def _extract_latest_sql_data(self, messages: List[BaseMessage]) -> Optional[str]:
        """从消息历史中提取最近的run_sql执行结果（同步版本）"""
        logger.info("🔍 提取最新的SQL执行结果...")
        
        # 查找最后一个HumanMessage之后的SQL执行结果
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
                
                try:
                    # 尝试解析JSON以验证格式
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