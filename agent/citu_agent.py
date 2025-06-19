# agent/citu_agent.py
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
from agent.classifier import QuestionClassifier
from agent.tools import TOOLS, generate_sql, execute_sql, generate_summary, general_chat
from agent.utils import get_compatible_llm

class CituLangGraphAgent:
    """Citu LangGraph智能助手主类 - 使用@tool装饰器 + Agent工具调用"""
    
    def __init__(self):
        # 加载配置
        try:
            from agent.config import get_current_config, get_nested_config
            self.config = get_current_config()
            print("[CITU_AGENT] 加载Agent配置完成")
        except ImportError:
            self.config = {}
            print("[CITU_AGENT] 配置文件不可用，使用默认配置")
        
        self.classifier = QuestionClassifier()
        self.tools = TOOLS
        self.llm = get_compatible_llm()
        
        # 预创建Agent实例以提升性能
        enable_reuse = self.config.get("performance", {}).get("enable_agent_reuse", True)
        if enable_reuse:
            print("[CITU_AGENT] 预创建Agent实例中...")
            self._database_executor = self._create_database_agent()
            self._chat_executor = self._create_chat_agent()
            print("[CITU_AGENT] Agent实例预创建完成")
        else:
            self._database_executor = None
            self._chat_executor = None
            print("[CITU_AGENT] Agent实例重用已禁用，将在运行时创建")
        
        self.workflow = self._create_workflow()
        print("[CITU_AGENT] LangGraph Agent with Tools初始化完成")
    
    def _create_workflow(self) -> StateGraph:
        """创建LangGraph工作流"""
        workflow = StateGraph(AgentState)
        
        # 添加节点
        workflow.add_node("classify_question", self._classify_question_node)
        workflow.add_node("agent_chat", self._agent_chat_node)
        workflow.add_node("agent_database", self._agent_database_node)
        workflow.add_node("format_response", self._format_response_node)
        
        # 设置入口点
        workflow.set_entry_point("classify_question")
        
        # 添加条件边：分类后的路由
        # 完全信任QuestionClassifier的决策，不再进行二次判断
        workflow.add_conditional_edges(
            "classify_question",
            self._route_after_classification,
            {
                "DATABASE": "agent_database",
                "CHAT": "agent_chat"  # CHAT分支处理所有非DATABASE的情况（包括UNCERTAIN）
            }
        )
        
        # 添加边
        workflow.add_edge("agent_chat", "format_response")
        workflow.add_edge("agent_database", "format_response")
        workflow.add_edge("format_response", END)
        
        return workflow.compile()
    
    def _classify_question_node(self, state: AgentState) -> AgentState:
        """问题分类节点"""
        try:
            print(f"[CLASSIFY_NODE] 开始分类问题: {state['question']}")
            
            classification_result = self.classifier.classify(state["question"])
            
            # 更新状态
            state["question_type"] = classification_result.question_type
            state["classification_confidence"] = classification_result.confidence
            state["classification_reason"] = classification_result.reason
            state["classification_method"] = classification_result.method
            state["current_step"] = "classified"
            state["execution_path"].append("classify")
            
            print(f"[CLASSIFY_NODE] 分类结果: {classification_result.question_type}, 置信度: {classification_result.confidence}")
            
            return state
            
        except Exception as e:
            print(f"[ERROR] 问题分类异常: {str(e)}")
            state["error"] = f"问题分类失败: {str(e)}"
            state["error_code"] = 500
            state["execution_path"].append("classify_error")
            return state
    
    def _create_database_agent(self):
        """创建数据库专用Agent（预创建）"""
        from agent.config import get_nested_config
        
        # 获取配置
        max_iterations = get_nested_config(self.config, "database_agent.max_iterations", 5)
        enable_verbose = get_nested_config(self.config, "database_agent.enable_verbose", True)
        early_stopping_method = get_nested_config(self.config, "database_agent.early_stopping_method", "generate")
        
        database_prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""
你是一个专业的数据库查询助手。你的任务是帮助用户查询数据库并生成报告。

工具使用流程：
1. 首先使用 generate_sql 工具将用户问题转换为SQL
2. 然后使用 execute_sql 工具执行SQL查询
3. 最后使用 generate_summary 工具为结果生成自然语言摘要

如果任何步骤失败，请提供清晰的错误信息并建议解决方案。
"""),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        database_tools = [generate_sql, execute_sql, generate_summary]
        agent = create_openai_tools_agent(self.llm, database_tools, database_prompt)
        
        return AgentExecutor(
            agent=agent,
            tools=database_tools,
            verbose=enable_verbose,
            handle_parsing_errors=True,
            max_iterations=max_iterations,
            early_stopping_method=early_stopping_method
        )
    
    def _agent_database_node(self, state: AgentState) -> AgentState:
        """数据库Agent节点 - 使用预创建或动态创建的Agent"""
        try:
            print(f"[DATABASE_AGENT] 开始处理数据库查询: {state['question']}")
            
            # 使用预创建的Agent或动态创建
            if self._database_executor is not None:
                executor = self._database_executor
                print(f"[DATABASE_AGENT] 使用预创建的Agent实例")
            else:
                executor = self._create_database_agent()
                print(f"[DATABASE_AGENT] 动态创建Agent实例")
            
            # 执行Agent
            result = executor.invoke({
                "input": state["question"]
            })
            
            # 解析Agent执行结果
            self._parse_database_agent_result(state, result)
            
            state["current_step"] = "database_completed"
            state["execution_path"].append("agent_database")
            
            print(f"[DATABASE_AGENT] 数据库查询完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] 数据库Agent异常: {str(e)}")
            state["error"] = f"数据库查询失败: {str(e)}"
            state["error_code"] = 500
            state["current_step"] = "database_error"
            state["execution_path"].append("agent_database_error")
            return state
    
    def _create_chat_agent(self):
        """创建聊天专用Agent（预创建）"""
        from agent.config import get_nested_config
        
        # 获取配置
        max_iterations = get_nested_config(self.config, "chat_agent.max_iterations", 3)
        enable_verbose = get_nested_config(self.config, "chat_agent.enable_verbose", True)
        
        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""
你是Citu智能数据问答平台的友好助手。

使用 general_chat 工具来处理用户的一般性问题、概念解释、操作指导等。

特别注意：
- 如果用户的问题可能涉及数据查询，建议他们尝试数据库查询功能
- 如果问题不够明确，主动询问更多细节以便更好地帮助用户
- 对于模糊的问题，可以提供多种可能的解决方案
- 当遇到不确定的问题时，通过友好的对话来澄清用户意图
"""),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        chat_tools = [general_chat]
        agent = create_openai_tools_agent(self.llm, chat_tools, chat_prompt)
        
        return AgentExecutor(
            agent=agent,
            tools=chat_tools,
            verbose=enable_verbose,
            handle_parsing_errors=True,
            max_iterations=max_iterations
        )
    
    def _agent_chat_node(self, state: AgentState) -> AgentState:
        """聊天Agent节点 - 使用预创建或动态创建的Agent"""
        try:
            print(f"[CHAT_AGENT] 开始处理聊天: {state['question']}")
            
            # 使用预创建的Agent或动态创建
            if self._chat_executor is not None:
                executor = self._chat_executor
                print(f"[CHAT_AGENT] 使用预创建的Agent实例")
            else:
                executor = self._create_chat_agent()
                print(f"[CHAT_AGENT] 动态创建Agent实例")
            
            # 构建上下文
            enable_context_injection = self.config.get("chat_agent", {}).get("enable_context_injection", True)
            context = None
            if enable_context_injection and state.get("classification_reason"):
                context = f"分类原因: {state['classification_reason']}"
            
            # 执行Agent
            input_text = state["question"]
            if context:
                input_text = f"{state['question']}\n\n上下文: {context}"
            
            result = executor.invoke({
                "input": input_text
            })
            
            # 提取聊天响应
            state["chat_response"] = result.get("output", "")
            state["current_step"] = "chat_completed"
            state["execution_path"].append("agent_chat")
            
            print(f"[CHAT_AGENT] 聊天处理完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] 聊天Agent异常: {str(e)}")
            state["chat_response"] = "抱歉，我暂时无法处理您的问题。请稍后再试，或者尝试询问数据相关的问题。"
            state["current_step"] = "chat_error"
            state["execution_path"].append("agent_chat_error")
            return state
    
    def _format_response_node(self, state: AgentState) -> AgentState:
        """格式化最终响应节点"""
        try:
            print(f"[FORMAT_NODE] 开始格式化响应，问题类型: {state['question_type']}")
            
            state["current_step"] = "completed"
            state["execution_path"].append("format_response")
            
            # 根据问题类型和执行状态格式化响应
            if state.get("error"):
                # 有错误的情况
                state["final_response"] = {
                    "success": False,
                    "error": state["error"],
                    "error_code": state.get("error_code", 500),
                    "question_type": state["question_type"],
                    "execution_path": state["execution_path"],
                    "classification_info": {
                        "confidence": state.get("classification_confidence", 0),
                        "reason": state.get("classification_reason", ""),
                        "method": state.get("classification_method", "")
                    }
                }
            
            elif state["question_type"] == "DATABASE":
                # 数据库查询类型
                if state.get("data_result") and state.get("summary"):
                    # 完整的数据库查询流程
                    state["final_response"] = {
                        "success": True,
                        "response": state["summary"],
                        "type": "DATABASE",
                        "sql": state.get("sql"),
                        "data_result": state["data_result"],
                        "summary": state["summary"],
                        "execution_path": state["execution_path"],
                        "classification_info": {
                            "confidence": state["classification_confidence"],
                            "reason": state["classification_reason"],
                            "method": state["classification_method"]
                        }
                    }
                else:
                    # 数据库查询失败，但有部分结果
                    state["final_response"] = {
                        "success": False,
                        "error": state.get("error", "数据库查询未完成"),
                        "type": "DATABASE",
                        "sql": state.get("sql"),
                        "execution_path": state["execution_path"]
                    }
            
            else:
                # 聊天类型
                state["final_response"] = {
                    "success": True,
                    "response": state.get("chat_response", ""),
                    "type": "CHAT",
                    "execution_path": state["execution_path"],
                    "classification_info": {
                        "confidence": state["classification_confidence"],
                        "reason": state["classification_reason"],
                        "method": state["classification_method"]
                    }
                }
            
            print(f"[FORMAT_NODE] 响应格式化完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] 响应格式化异常: {str(e)}")
            state["final_response"] = {
                "success": False,
                "error": f"响应格式化异常: {str(e)}",
                "error_code": 500,
                "execution_path": state["execution_path"]
            }
            return state
    
    def _route_after_classification(self, state: AgentState) -> Literal["DATABASE", "CHAT"]:
        """
        分类后的路由决策
        
        完全信任QuestionClassifier的决策：
        - DATABASE类型 → 数据库Agent
        - CHAT和UNCERTAIN类型 → 聊天Agent
        
        这样避免了双重决策的冲突，所有分类逻辑都集中在QuestionClassifier中
        """
        question_type = state["question_type"]
        confidence = state["classification_confidence"]
        
        print(f"[ROUTE] 分类路由: {question_type}, 置信度: {confidence} (完全信任分类器决策)")
        
        if question_type == "DATABASE":
            return "DATABASE"
        else:
            # 将 "CHAT" 和 "UNCERTAIN" 类型都路由到聊天流程
            # 聊天Agent可以处理不确定的情况，并在必要时引导用户提供更多信息
            return "CHAT"
    
    def _parse_database_agent_result(self, state: AgentState, agent_result: Dict[str, Any]):
        """解析数据库Agent的执行结果"""
        try:
            output = agent_result.get("output", "")
            intermediate_steps = agent_result.get("intermediate_steps", [])
            
            # 从intermediate_steps中提取工具调用结果
            for step in intermediate_steps:
                if len(step) >= 2:
                    action, observation = step[0], step[1]
                    
                    if hasattr(action, 'tool') and hasattr(action, 'tool_input'):
                        tool_name = action.tool
                        tool_result = observation
                        
                        # 解析工具结果
                        if tool_name == "generate_sql" and isinstance(tool_result, dict):
                            if tool_result.get("success"):
                                state["sql"] = tool_result.get("sql")
                            else:
                                state["error"] = tool_result.get("error")
                        
                        elif tool_name == "execute_sql" and isinstance(tool_result, dict):
                            if tool_result.get("success"):
                                state["data_result"] = tool_result.get("data_result")
                            else:
                                state["error"] = tool_result.get("error")
                        
                        elif tool_name == "generate_summary" and isinstance(tool_result, dict):
                            if tool_result.get("success"):
                                state["summary"] = tool_result.get("summary")
            
            # 如果没有从工具结果中获取到摘要，使用Agent的最终输出
            if not state.get("summary") and output:
                state["summary"] = output
                
        except Exception as e:
            print(f"[WARNING] 解析数据库Agent结果失败: {str(e)}")
            # 使用Agent的输出作为摘要
            state["summary"] = agent_result.get("output", "查询处理完成")
    
    def process_question(self, question: str, session_id: str = None) -> Dict[str, Any]:
        """
        统一的问题处理入口
        
        Args:
            question: 用户问题
            session_id: 会话ID
            
        Returns:
            Dict包含完整的处理结果
        """
        try:
            print(f"[CITU_AGENT] 开始处理问题: {question}")
            
            # 初始化状态
            initial_state = self._create_initial_state(question, session_id)
            
            # 执行工作流
            final_state = self.workflow.invoke(
                initial_state,
                config={
                    "configurable": {"session_id": session_id}
                } if session_id else None
            )
            
            # 提取最终结果
            result = final_state["final_response"]
            
            print(f"[CITU_AGENT] 问题处理完成: {result.get('success', False)}")
            
            return result
            
        except Exception as e:
            print(f"[ERROR] Agent执行异常: {str(e)}")
            return {
                "success": False,
                "error": f"Agent系统异常: {str(e)}",
                "error_code": 500,
                "execution_path": ["error"]
            }
    
    def _create_initial_state(self, question: str, session_id: str = None) -> AgentState:
        """创建初始状态"""
        return AgentState(
            # 输入信息
            question=question,
            session_id=session_id,
            
            # 分类结果
            question_type="",
            classification_confidence=0.0,
            classification_reason="",
            classification_method="",
            
            # 数据库查询流程状态
            sql=None,
            sql_generation_attempts=0,
            data_result=None,
            summary=None,
            
            # 聊天响应
            chat_response=None,
            
            # 最终输出
            final_response={},
            
            # 错误处理
            error=None,
            error_code=None,
            
            # 流程控制
            current_step="start",
            execution_path=[],
            retry_count=0,
            max_retries=2,
            
            # 调试信息
            debug_info={}
        )
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 从配置获取健康检查参数
            from agent.config import get_nested_config
            test_question = get_nested_config(self.config, "health_check.test_question", "你好")
            enable_full_test = get_nested_config(self.config, "health_check.enable_full_test", True)
            
            if enable_full_test:
                # 完整流程测试
                test_result = self.process_question(test_question, "health_check")
                
                return {
                    "status": "healthy" if test_result.get("success") else "degraded",
                    "test_result": test_result.get("success", False),
                    "workflow_compiled": self.workflow is not None,
                    "tools_count": len(self.tools),
                    "agent_reuse_enabled": self._database_executor is not None and self._chat_executor is not None,
                    "message": "Agent健康检查完成"
                }
            else:
                # 简单检查
                return {
                    "status": "healthy",
                    "test_result": True,
                    "workflow_compiled": self.workflow is not None,
                    "tools_count": len(self.tools),
                    "agent_reuse_enabled": self._database_executor is not None and self._chat_executor is not None,
                    "message": "Agent简单健康检查完成"
                }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "workflow_compiled": self.workflow is not None,
                "tools_count": len(self.tools) if hasattr(self, 'tools') else 0,
                "agent_reuse_enabled": False,
                "message": "Agent健康检查失败"
            }