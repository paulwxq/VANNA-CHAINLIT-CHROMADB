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
from app_config import ENABLE_RESULT_SUMMARY

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
        
        # 注意：现在使用直接工具调用模式，不再需要预创建Agent执行器
        print("[CITU_AGENT] 使用直接工具调用模式")
        
        # 不在构造时创建workflow，改为动态创建以支持路由模式参数
        # self.workflow = self._create_workflow()
        print("[CITU_AGENT] LangGraph Agent with Direct Tools初始化完成")
    
    def _create_workflow(self, routing_mode: str = None) -> StateGraph:
        """根据路由模式创建不同的工作流"""
        # 确定使用的路由模式
        if routing_mode:
            QUESTION_ROUTING_MODE = routing_mode
            print(f"[CITU_AGENT] 创建工作流，使用传入的路由模式: {QUESTION_ROUTING_MODE}")
        else:
            try:
                from app_config import QUESTION_ROUTING_MODE
                print(f"[CITU_AGENT] 创建工作流，使用配置文件路由模式: {QUESTION_ROUTING_MODE}")
            except ImportError:
                QUESTION_ROUTING_MODE = "hybrid"
                print(f"[CITU_AGENT] 配置导入失败，使用默认路由模式: {QUESTION_ROUTING_MODE}")
        
        workflow = StateGraph(AgentState)
        
        # 根据路由模式创建不同的工作流
        if QUESTION_ROUTING_MODE == "database_direct":
            # 直接数据库模式：跳过分类，直接进入数据库处理
            workflow.add_node("init_direct_database", self._init_direct_database_node)
            workflow.add_node("agent_database", self._agent_database_node)
            workflow.add_node("format_response", self._format_response_node)
            
            workflow.set_entry_point("init_direct_database")
            workflow.add_edge("init_direct_database", "agent_database")
            workflow.add_edge("agent_database", "format_response")
            workflow.add_edge("format_response", END)
            
        elif QUESTION_ROUTING_MODE == "chat_direct":
            # 直接聊天模式：跳过分类，直接进入聊天处理
            workflow.add_node("init_direct_chat", self._init_direct_chat_node)
            workflow.add_node("agent_chat", self._agent_chat_node)
            workflow.add_node("format_response", self._format_response_node)
            
            workflow.set_entry_point("init_direct_chat")
            workflow.add_edge("init_direct_chat", "agent_chat")
            workflow.add_edge("agent_chat", "format_response")
            workflow.add_edge("format_response", END)
            
        else:
            # 其他模式(hybrid, llm_only)：使用原有的分类工作流
            workflow.add_node("classify_question", self._classify_question_node)
            workflow.add_node("agent_chat", self._agent_chat_node)
            workflow.add_node("agent_database", self._agent_database_node)
            workflow.add_node("format_response", self._format_response_node)
            
            workflow.set_entry_point("classify_question")
            
            # 添加条件边：分类后的路由
            workflow.add_conditional_edges(
                "classify_question",
                self._route_after_classification,
                {
                    "DATABASE": "agent_database",
                    "CHAT": "agent_chat"
                }
            )
            
            workflow.add_edge("agent_chat", "format_response")
            workflow.add_edge("agent_database", "format_response")
            workflow.add_edge("format_response", END)
        
        return workflow.compile()
    
    def _init_direct_database_node(self, state: AgentState) -> AgentState:
        """初始化直接数据库模式的状态"""
        try:
            # 从state中获取路由模式，而不是从配置文件读取
            routing_mode = state.get("routing_mode", "database_direct")
            
            # 设置直接数据库模式的分类状态
            state["question_type"] = "DATABASE"
            state["classification_confidence"] = 1.0
            state["classification_reason"] = "配置为直接数据库查询模式"
            state["classification_method"] = "direct_database"
            state["routing_mode"] = routing_mode
            state["current_step"] = "direct_database_init"
            state["execution_path"].append("init_direct_database")
            
            print(f"[DIRECT_DATABASE] 直接数据库模式初始化完成")
            
            return state
            
        except Exception as e:
            print(f"[ERROR] 直接数据库模式初始化异常: {str(e)}")
            state["error"] = f"直接数据库模式初始化失败: {str(e)}"
            state["error_code"] = 500
            state["execution_path"].append("init_direct_database_error")
            return state

    def _init_direct_chat_node(self, state: AgentState) -> AgentState:
        """初始化直接聊天模式的状态"""
        try:
            # 从state中获取路由模式，而不是从配置文件读取
            routing_mode = state.get("routing_mode", "chat_direct")
            
            # 设置直接聊天模式的分类状态
            state["question_type"] = "CHAT"
            state["classification_confidence"] = 1.0
            state["classification_reason"] = "配置为直接聊天模式"
            state["classification_method"] = "direct_chat"
            state["routing_mode"] = routing_mode
            state["current_step"] = "direct_chat_init"
            state["execution_path"].append("init_direct_chat")
            
            print(f"[DIRECT_CHAT] 直接聊天模式初始化完成")
            
            return state
            
        except Exception as e:
            print(f"[ERROR] 直接聊天模式初始化异常: {str(e)}")
            state["error"] = f"直接聊天模式初始化失败: {str(e)}"
            state["error_code"] = 500
            state["execution_path"].append("init_direct_chat_error")
            return state
    
    def _classify_question_node(self, state: AgentState) -> AgentState:
        """问题分类节点 - 支持渐进式分类策略"""
        try:
            # 从state中获取路由模式，而不是从配置文件读取
            routing_mode = state.get("routing_mode", "hybrid")
            
            print(f"[CLASSIFY_NODE] 开始分类问题: {state['question']}")
            
            # 获取上下文类型（如果有的话）
            context_type = state.get("context_type")
            if context_type:
                print(f"[CLASSIFY_NODE] 检测到上下文类型: {context_type}")
            
            # 使用渐进式分类策略，传递路由模式
            classification_result = self.classifier.classify(state["question"], context_type, routing_mode)
            
            # 更新状态
            state["question_type"] = classification_result.question_type
            state["classification_confidence"] = classification_result.confidence
            state["classification_reason"] = classification_result.reason
            state["classification_method"] = classification_result.method
            state["routing_mode"] = routing_mode
            state["current_step"] = "classified"
            state["execution_path"].append("classify")
            
            print(f"[CLASSIFY_NODE] 分类结果: {classification_result.question_type}, 置信度: {classification_result.confidence}")
            print(f"[CLASSIFY_NODE] 路由模式: {routing_mode}, 分类方法: {classification_result.method}")
            
            return state
            
        except Exception as e:
            print(f"[ERROR] 问题分类异常: {str(e)}")
            state["error"] = f"问题分类失败: {str(e)}"
            state["error_code"] = 500
            state["execution_path"].append("classify_error")
            return state
        
    def _agent_database_node(self, state: AgentState) -> AgentState:
        """数据库Agent节点 - 直接工具调用模式"""
        try:
            print(f"[DATABASE_AGENT] 开始处理数据库查询: {state['question']}")
            
            question = state["question"]
            
            # 步骤1：生成SQL
            print(f"[DATABASE_AGENT] 步骤1：生成SQL")
            sql_result = generate_sql.invoke({"question": question, "allow_llm_to_see_data": True})
            
            if not sql_result.get("success"):
                print(f"[DATABASE_AGENT] SQL生成失败: {sql_result.get('error')}")
                state["error"] = sql_result.get("error", "SQL生成失败")
                state["error_code"] = 500
                state["current_step"] = "database_error"
                state["execution_path"].append("agent_database_error")
                return state
            
            sql = sql_result.get("sql")
            state["sql"] = sql
            print(f"[DATABASE_AGENT] SQL生成成功: {sql}")
            
            # 步骤1.5：检查是否为解释性响应而非SQL
            error_type = sql_result.get("error_type")
            if error_type == "llm_explanation":
                # LLM返回了解释性文本，直接作为最终答案
                explanation = sql_result.get("error", "")
                state["chat_response"] = explanation + " 请尝试提问其它问题。"
                state["current_step"] = "database_completed"
                state["execution_path"].append("agent_database")
                print(f"[DATABASE_AGENT] 返回LLM解释性答案: {explanation}")
                return state
            
            # 额外验证：检查SQL格式（防止工具误判）
            from agent.utils import _is_valid_sql_format
            if not _is_valid_sql_format(sql):
                # 内容看起来不是SQL，当作解释性响应处理
                state["chat_response"] = sql + " 请尝试提问其它问题。"
                state["current_step"] = "database_completed"  
                state["execution_path"].append("agent_database")
                print(f"[DATABASE_AGENT] 内容不是有效SQL，当作解释返回: {sql}")
                return state
            
            # 步骤2：执行SQL
            print(f"[DATABASE_AGENT] 步骤2：执行SQL")
            execute_result = execute_sql.invoke({"sql": sql})
            
            if not execute_result.get("success"):
                print(f"[DATABASE_AGENT] SQL执行失败: {execute_result.get('error')}")
                state["error"] = execute_result.get("error", "SQL执行失败")
                state["error_code"] = 500
                state["current_step"] = "database_error"
                state["execution_path"].append("agent_database_error")
                return state
            
            query_result = execute_result.get("data_result")
            state["query_result"] = query_result
            print(f"[DATABASE_AGENT] SQL执行成功，返回 {query_result.get('row_count', 0)} 行数据")
            
            # 步骤3：生成摘要（可通过配置控制，仅在有数据时生成）
            if ENABLE_RESULT_SUMMARY and query_result.get('row_count', 0) > 0:
                print(f"[DATABASE_AGENT] 步骤3：生成摘要")
                
                # 重要：提取原始问题用于摘要生成，避免历史记录循环嵌套
                original_question = self._extract_original_question(question)
                print(f"[DATABASE_AGENT] 原始问题: {original_question}")
                
                summary_result = generate_summary.invoke({
                    "question": original_question,  # 使用原始问题而不是enhanced_question
                    "query_result": query_result,
                    "sql": sql
                })
                
                if not summary_result.get("success"):
                    print(f"[DATABASE_AGENT] 摘要生成失败: {summary_result.get('message')}")
                    # 摘要生成失败不是致命错误，使用默认摘要
                    state["summary"] = f"查询执行完成，共返回 {query_result.get('row_count', 0)} 条记录。"
                else:
                    state["summary"] = summary_result.get("summary")
                    print(f"[DATABASE_AGENT] 摘要生成成功")
            else:
                print(f"[DATABASE_AGENT] 跳过摘要生成（ENABLE_RESULT_SUMMARY={ENABLE_RESULT_SUMMARY}，数据行数={query_result.get('row_count', 0)}）")
                # 不生成摘要时，不设置summary字段，让格式化响应节点决定如何处理
            
            state["current_step"] = "database_completed"
            state["execution_path"].append("agent_database")
            
            print(f"[DATABASE_AGENT] 数据库查询完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] 数据库Agent异常: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
            state["error"] = f"数据库查询失败: {str(e)}"
            state["error_code"] = 500
            state["current_step"] = "database_error"
            state["execution_path"].append("agent_database_error")
            return state
    
    def _agent_chat_node(self, state: AgentState) -> AgentState:
        """聊天Agent节点 - 直接工具调用模式"""
        try:
            print(f"[CHAT_AGENT] 开始处理聊天: {state['question']}")
            
            question = state["question"]
            
            # 构建上下文 - 仅使用真实的对话历史上下文
            # 注意：不要将分类原因传递给LLM，那是系统内部的路由信息
            enable_context_injection = self.config.get("chat_agent", {}).get("enable_context_injection", True)
            context = None
            if enable_context_injection:
                # TODO: 在这里可以添加真实的对话历史上下文
                # 例如从Redis或其他存储中获取最近的对话记录
                # context = get_conversation_history(state.get("session_id"))
                pass
            
            # 直接调用general_chat工具
            print(f"[CHAT_AGENT] 调用general_chat工具")
            chat_result = general_chat.invoke({
                "question": question,
                "context": context
            })
            
            if chat_result.get("success"):
                state["chat_response"] = chat_result.get("response", "")
                print(f"[CHAT_AGENT] 聊天处理成功")
            else:
                # 处理失败，使用备用响应
                state["chat_response"] = chat_result.get("response", "抱歉，我暂时无法处理您的问题。请稍后再试。")
                print(f"[CHAT_AGENT] 聊天处理失败，使用备用响应: {chat_result.get('error')}")
            
            state["current_step"] = "chat_completed"
            state["execution_path"].append("agent_chat")
            
            print(f"[CHAT_AGENT] 聊天处理完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] 聊天Agent异常: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
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
                if state.get("chat_response"):
                    # SQL生成失败的解释性响应（不受ENABLE_RESULT_SUMMARY配置影响）
                    state["final_response"] = {
                        "success": True,
                        "response": state["chat_response"],
                        "type": "DATABASE",
                        "sql": state.get("sql"),
                        "query_result": state.get("query_result"),  # 获取query_result字段
                        "execution_path": state["execution_path"],
                        "classification_info": {
                            "confidence": state["classification_confidence"],
                            "reason": state["classification_reason"],
                            "method": state["classification_method"]
                        }
                    }
                elif state.get("summary"):
                    # 正常的数据库查询结果，有摘要的情况
                    # 将summary的值同时赋给response字段（为将来移除summary字段做准备）
                    state["final_response"] = {
                        "success": True,
                        "type": "DATABASE",
                        "response": state["summary"],  # 新增：将summary的值赋给response
                        "sql": state.get("sql"),
                        "query_result": state.get("query_result"),  # 获取query_result字段
                        "summary": state["summary"],  # 暂时保留summary字段
                        "execution_path": state["execution_path"],
                        "classification_info": {
                            "confidence": state["classification_confidence"],
                            "reason": state["classification_reason"],
                            "method": state["classification_method"]
                        }
                    }
                elif state.get("query_result"):
                    # 有数据但没有摘要（摘要被配置禁用）
                    query_result = state.get("query_result")
                    row_count = query_result.get("row_count", 0)
                    
                    # 构建基本响应，不包含summary字段和response字段
                    # 用户应该直接从query_result.columns和query_result.rows获取数据
                    state["final_response"] = {
                        "success": True,
                        "type": "DATABASE",
                        "sql": state.get("sql"),
                        "query_result": query_result,  # 获取query_result字段
                        "execution_path": state["execution_path"],
                        "classification_info": {
                            "confidence": state["classification_confidence"],
                            "reason": state["classification_reason"],
                            "method": state["classification_method"]
                        }
                    }
                else:
                    # 数据库查询失败，没有任何结果
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
    
    def process_question(self, question: str, session_id: str = None, context_type: str = None, routing_mode: str = None) -> Dict[str, Any]:
        """
        统一的问题处理入口
        
        Args:
            question: 用户问题
            session_id: 会话ID
            context_type: 上下文类型 ("DATABASE" 或 "CHAT")，用于渐进式分类
            routing_mode: 路由模式，可选，用于覆盖配置文件设置
            
        Returns:
            Dict包含完整的处理结果
        """
        try:
            print(f"[CITU_AGENT] 开始处理问题: {question}")
            if context_type:
                print(f"[CITU_AGENT] 上下文类型: {context_type}")
            if routing_mode:
                print(f"[CITU_AGENT] 使用指定路由模式: {routing_mode}")
            
            # 动态创建workflow（基于路由模式）
            workflow = self._create_workflow(routing_mode)
            
            # 初始化状态
            initial_state = self._create_initial_state(question, session_id, context_type, routing_mode)
            
            # 执行工作流
            final_state = workflow.invoke(
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
    
    def _create_initial_state(self, question: str, session_id: str = None, context_type: str = None, routing_mode: str = None) -> AgentState:
        """创建初始状态 - 支持渐进式分类"""
        # 确定使用的路由模式
        if routing_mode:
            effective_routing_mode = routing_mode
        else:
            try:
                from app_config import QUESTION_ROUTING_MODE
                effective_routing_mode = QUESTION_ROUTING_MODE
            except ImportError:
                effective_routing_mode = "hybrid"
        
        return AgentState(
            # 输入信息
            question=question,
            session_id=session_id,
            
            # 上下文信息
            context_type=context_type,
            
            # 分类结果 (初始值，会在分类节点或直接模式初始化节点中更新)
            question_type="UNCERTAIN",
            classification_confidence=0.0,
            classification_reason="",
            classification_method="",
            
            # 数据库查询流程状态
            sql=None,
            sql_generation_attempts=0,
            query_result=None,
            summary=None,
            
            # 聊天响应
            chat_response=None,
            
            # 最终输出
            final_response={},
            
            # 错误处理
            error=None,
            error_code=None,
            
            # 流程控制
            current_step="initialized",
            execution_path=["start"],
            retry_count=0,
            max_retries=3,
            
            # 调试信息
            debug_info={},
            
            # 路由模式
            routing_mode=effective_routing_mode
        )
    
    def _extract_original_question(self, question: str) -> str:
        """
        从enhanced_question中提取原始问题
        
        Args:
            question: 可能包含上下文的问题
            
        Returns:
            str: 原始问题
        """
        try:
            # 检查是否为enhanced_question格式
            if "\n[CONTEXT]\n" in question and "\n[CURRENT]\n" in question:
                # 提取[CURRENT]标签后的内容
                current_start = question.find("\n[CURRENT]\n")
                if current_start != -1:
                    original_question = question[current_start + len("\n[CURRENT]\n"):].strip()
                    return original_question
            
            # 如果不是enhanced_question格式，直接返回原问题
            return question.strip()
            
        except Exception as e:
            print(f"[WARNING] 提取原始问题失败: {str(e)}")
            return question.strip()

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
                    "workflow_compiled": True,  # 动态创建，始终可用
                    "tools_count": len(self.tools),
                    "agent_reuse_enabled": False,
                    "message": "Agent健康检查完成"
                }
            else:
                # 简单检查
                return {
                    "status": "healthy",
                    "test_result": True,
                    "workflow_compiled": True,  # 动态创建，始终可用
                    "tools_count": len(self.tools),
                    "agent_reuse_enabled": False,
                    "message": "Agent简单健康检查完成"
                }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "workflow_compiled": True,  # 动态创建，始终可用
                "tools_count": len(self.tools) if hasattr(self, 'tools') else 0,
                "agent_reuse_enabled": False,
                "message": "Agent健康检查失败"
            }