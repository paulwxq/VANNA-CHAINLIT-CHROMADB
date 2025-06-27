# agent/citu_agent.py
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
from agent.classifier import QuestionClassifier
from agent.tools import TOOLS, generate_sql, execute_sql, generate_summary, general_chat
from agent.tools.utils import get_compatible_llm
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
            # 直接数据库模式：跳过分类，直接进入数据库处理（使用新的拆分节点）
            workflow.add_node("init_direct_database", self._init_direct_database_node)
            workflow.add_node("agent_sql_generation", self._agent_sql_generation_node)
            workflow.add_node("agent_sql_execution", self._agent_sql_execution_node)
            workflow.add_node("format_response", self._format_response_node)
            
            workflow.set_entry_point("init_direct_database")
            
            # 添加条件路由
            workflow.add_edge("init_direct_database", "agent_sql_generation")
            workflow.add_conditional_edges(
                "agent_sql_generation",
                self._route_after_sql_generation,
                {
                    "continue_execution": "agent_sql_execution",
                    "return_to_user": "format_response"
                }
            )
            workflow.add_edge("agent_sql_execution", "format_response")
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
            # 其他模式(hybrid, llm_only)：使用新的拆分工作流
            workflow.add_node("classify_question", self._classify_question_node)
            workflow.add_node("agent_chat", self._agent_chat_node)
            workflow.add_node("agent_sql_generation", self._agent_sql_generation_node)
            workflow.add_node("agent_sql_execution", self._agent_sql_execution_node)
            workflow.add_node("format_response", self._format_response_node)
            
            workflow.set_entry_point("classify_question")
            
            # 添加条件边：分类后的路由
            workflow.add_conditional_edges(
                "classify_question",
                self._route_after_classification,
                {
                    "DATABASE": "agent_sql_generation",
                    "CHAT": "agent_chat"
                }
            )
            
            # 添加条件边：SQL生成后的路由
            workflow.add_conditional_edges(
                "agent_sql_generation",
                self._route_after_sql_generation,
                {
                    "continue_execution": "agent_sql_execution",
                    "return_to_user": "format_response"
                }
            )
            
            # 普通边
            workflow.add_edge("agent_chat", "format_response")
            workflow.add_edge("agent_sql_execution", "format_response")
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
        
    async def _agent_sql_generation_node(self, state: AgentState) -> AgentState:
        """SQL生成验证节点 - 负责生成SQL、验证SQL和决定路由"""
        try:
            print(f"[SQL_GENERATION] 开始处理SQL生成和验证: {state['question']}")
            
            question = state["question"]
            
            # 步骤1：生成SQL
            print(f"[SQL_GENERATION] 步骤1：生成SQL")
            sql_result = generate_sql.invoke({"question": question, "allow_llm_to_see_data": True})
            
            if not sql_result.get("success"):
                # SQL生成失败的统一处理
                error_message = sql_result.get("error", "")
                error_type = sql_result.get("error_type", "")
                
                print(f"[SQL_GENERATION] SQL生成失败: {error_message}")
                
                # 根据错误类型生成用户提示
                if "no relevant tables" in error_message.lower() or "table not found" in error_message.lower():
                    user_prompt = "数据库中没有相关的表或字段信息，请您提供更多具体信息或修改问题。"
                    failure_reason = "missing_database_info"
                elif "ambiguous" in error_message.lower() or "more information" in error_message.lower():
                    user_prompt = "您的问题需要更多信息才能准确查询，请提供更详细的描述。"
                    failure_reason = "ambiguous_question"
                elif error_type == "llm_explanation":
                    user_prompt = error_message + " 请尝试重新描述您的问题或询问其他内容。"
                    failure_reason = "llm_explanation"
                else:
                    user_prompt = "无法生成有效的SQL查询，请尝试重新描述您的问题。"
                    failure_reason = "unknown_generation_failure"
                
                # 统一返回失败状态
                state["sql_generation_success"] = False
                state["user_prompt"] = user_prompt
                state["validation_error_type"] = failure_reason
                state["current_step"] = "sql_generation_failed"
                state["execution_path"].append("agent_sql_generation_failed")
                
                print(f"[SQL_GENERATION] 生成失败: {failure_reason} - {user_prompt}")
                return state
            
            sql = sql_result.get("sql")
            state["sql"] = sql
            print(f"[SQL_GENERATION] SQL生成成功: {sql}")
            
            # 步骤1.5：检查是否为解释性响应而非SQL
            error_type = sql_result.get("error_type")
            if error_type == "llm_explanation":
                # LLM返回了解释性文本，直接作为最终答案
                explanation = sql_result.get("error", "")
                state["chat_response"] = explanation + " 请尝试提问其它问题。"
                state["sql_generation_success"] = False
                state["validation_error_type"] = "llm_explanation"
                state["current_step"] = "sql_generation_completed"
                state["execution_path"].append("agent_sql_generation")
                print(f"[SQL_GENERATION] 返回LLM解释性答案: {explanation}")
                return state
            
            # 额外验证：检查SQL格式（防止工具误判）
            from agent.tools.utils import _is_valid_sql_format
            if not _is_valid_sql_format(sql):
                # 内容看起来不是SQL，当作解释性响应处理
                state["chat_response"] = sql + " 请尝试提问其它问题。"
                state["sql_generation_success"] = False
                state["validation_error_type"] = "invalid_sql_format"
                state["current_step"] = "sql_generation_completed"  
                state["execution_path"].append("agent_sql_generation")
                print(f"[SQL_GENERATION] 内容不是有效SQL，当作解释返回: {sql}")
                return state
            
            # 步骤2：SQL验证（如果启用）
            if self._is_sql_validation_enabled():
                print(f"[SQL_GENERATION] 步骤2：验证SQL")
                validation_result = await self._validate_sql_with_custom_priority(sql)
                
                if not validation_result.get("valid"):
                    # 验证失败，检查是否可以修复
                    error_type = validation_result.get("error_type")
                    error_message = validation_result.get("error_message")
                    can_repair = validation_result.get("can_repair", False)
                    
                    print(f"[SQL_GENERATION] SQL验证失败: {error_type} - {error_message}")
                    
                    if error_type == "forbidden_keywords":
                        # 禁止词错误，直接失败，不尝试修复
                        state["sql_generation_success"] = False
                        state["sql_validation_success"] = False
                        state["user_prompt"] = error_message
                        state["validation_error_type"] = "forbidden_keywords"
                        state["current_step"] = "sql_validation_failed"
                        state["execution_path"].append("forbidden_keywords_failed")
                        print(f"[SQL_GENERATION] 禁止词验证失败，直接结束")
                        return state
                    
                    elif error_type == "syntax_error" and can_repair and self._is_auto_repair_enabled():
                        # 语法错误，尝试修复（仅一次）
                        print(f"[SQL_GENERATION] 尝试修复SQL语法错误(仅一次): {error_message}")
                        state["sql_repair_attempted"] = True
                        
                        repair_result = await self._attempt_sql_repair_once(sql, error_message)
                        
                        if repair_result.get("success"):
                            # 修复成功
                            repaired_sql = repair_result.get("repaired_sql")
                            state["sql"] = repaired_sql
                            state["sql_generation_success"] = True
                            state["sql_validation_success"] = True
                            state["sql_repair_success"] = True
                            state["current_step"] = "sql_generation_completed"
                            state["execution_path"].append("sql_repair_success")
                            print(f"[SQL_GENERATION] SQL修复成功: {repaired_sql}")
                            return state
                        else:
                            # 修复失败，直接结束
                            repair_error = repair_result.get("error", "修复失败")
                            print(f"[SQL_GENERATION] SQL修复失败: {repair_error}")
                            state["sql_generation_success"] = False
                            state["sql_validation_success"] = False
                            state["sql_repair_success"] = False
                            state["user_prompt"] = f"SQL语法修复失败: {repair_error}"
                            state["validation_error_type"] = "syntax_repair_failed"
                            state["current_step"] = "sql_repair_failed"
                            state["execution_path"].append("sql_repair_failed")
                            return state
                    else:
                        # 不启用修复或其他错误类型，直接失败
                        state["sql_generation_success"] = False
                        state["sql_validation_success"] = False
                        state["user_prompt"] = f"SQL验证失败: {error_message}"
                        state["validation_error_type"] = error_type
                        state["current_step"] = "sql_validation_failed"
                        state["execution_path"].append("sql_validation_failed")
                        print(f"[SQL_GENERATION] SQL验证失败，不尝试修复")
                        return state
                else:
                    print(f"[SQL_GENERATION] SQL验证通过")
                    state["sql_validation_success"] = True
            else:
                print(f"[SQL_GENERATION] 跳过SQL验证（未启用）")
                state["sql_validation_success"] = True
            
            # 生成和验证都成功
            state["sql_generation_success"] = True
            state["current_step"] = "sql_generation_completed"
            state["execution_path"].append("agent_sql_generation")
            
            print(f"[SQL_GENERATION] SQL生成验证完成，准备执行")
            return state
            
        except Exception as e:
            print(f"[ERROR] SQL生成验证节点异常: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
            state["sql_generation_success"] = False
            state["sql_validation_success"] = False
            state["user_prompt"] = f"SQL生成验证异常: {str(e)}"
            state["validation_error_type"] = "node_exception"
            state["current_step"] = "sql_generation_error"
            state["execution_path"].append("agent_sql_generation_error")
            return state

    def _agent_sql_execution_node(self, state: AgentState) -> AgentState:
        """SQL执行节点 - 负责执行已验证的SQL和生成摘要"""
        try:
            print(f"[SQL_EXECUTION] 开始执行SQL: {state.get('sql', 'N/A')}")
            
            sql = state.get("sql")
            question = state["question"]
            
            if not sql:
                print(f"[SQL_EXECUTION] 没有可执行的SQL")
                state["error"] = "没有可执行的SQL语句"
                state["error_code"] = 500
                state["current_step"] = "sql_execution_error"
                state["execution_path"].append("agent_sql_execution_error")
                return state
            
            # 步骤1：执行SQL
            print(f"[SQL_EXECUTION] 步骤1：执行SQL")
            execute_result = execute_sql.invoke({"sql": sql})
            
            if not execute_result.get("success"):
                print(f"[SQL_EXECUTION] SQL执行失败: {execute_result.get('error')}")
                state["error"] = execute_result.get("error", "SQL执行失败")
                state["error_code"] = 500
                state["current_step"] = "sql_execution_error"
                state["execution_path"].append("agent_sql_execution_error")
                return state
            
            query_result = execute_result.get("data_result")
            state["query_result"] = query_result
            print(f"[SQL_EXECUTION] SQL执行成功，返回 {query_result.get('row_count', 0)} 行数据")
            
            # 步骤2：生成摘要（根据配置和数据情况）
            if ENABLE_RESULT_SUMMARY and query_result.get('row_count', 0) > 0:
                print(f"[SQL_EXECUTION] 步骤2：生成摘要")
                
                # 重要：提取原始问题用于摘要生成，避免历史记录循环嵌套
                original_question = self._extract_original_question(question)
                print(f"[SQL_EXECUTION] 原始问题: {original_question}")
                
                summary_result = generate_summary.invoke({
                    "question": original_question,  # 使用原始问题而不是enhanced_question
                    "query_result": query_result,
                    "sql": sql
                })
                
                if not summary_result.get("success"):
                    print(f"[SQL_EXECUTION] 摘要生成失败: {summary_result.get('message')}")
                    # 摘要生成失败不是致命错误，使用默认摘要
                    state["summary"] = f"查询执行完成，共返回 {query_result.get('row_count', 0)} 条记录。"
                else:
                    state["summary"] = summary_result.get("summary")
                    print(f"[SQL_EXECUTION] 摘要生成成功")
            else:
                print(f"[SQL_EXECUTION] 跳过摘要生成（ENABLE_RESULT_SUMMARY={ENABLE_RESULT_SUMMARY}，数据行数={query_result.get('row_count', 0)}）")
                # 不生成摘要时，不设置summary字段，让格式化响应节点决定如何处理
            
            state["current_step"] = "sql_execution_completed"
            state["execution_path"].append("agent_sql_execution")
            
            print(f"[SQL_EXECUTION] SQL执行完成")
            return state
            
        except Exception as e:
            print(f"[ERROR] SQL执行节点异常: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
            state["error"] = f"SQL执行失败: {str(e)}"
            state["error_code"] = 500
            state["current_step"] = "sql_execution_error"
            state["execution_path"].append("agent_sql_execution_error")
            return state

    def _agent_database_node(self, state: AgentState) -> AgentState:
        """
        数据库Agent节点 - 直接工具调用模式 [已废弃]
        
        注意：此方法已被拆分为 _agent_sql_generation_node 和 _agent_sql_execution_node
        保留此方法仅为向后兼容，新的工作流使用拆分后的节点
        """
        try:
            print(f"[DATABASE_AGENT] ⚠️  使用已废弃的database节点，建议使用新的拆分节点")
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
            from agent.tools.utils import _is_valid_sql_format
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
                
                # 处理SQL生成失败的情况
                if not state.get("sql_generation_success", True) and state.get("user_prompt"):
                    state["final_response"] = {
                        "success": False,
                        "response": state["user_prompt"],
                        "type": "DATABASE",
                        "sql_generation_failed": True,
                        "validation_error_type": state.get("validation_error_type"),
                        "sql": state.get("sql"),
                        "execution_path": state["execution_path"],
                        "classification_info": {
                            "confidence": state["classification_confidence"],
                            "reason": state["classification_reason"],
                            "method": state["classification_method"]
                        },
                        "sql_validation_info": {
                            "sql_generation_success": state.get("sql_generation_success", False),
                            "sql_validation_success": state.get("sql_validation_success", False),
                            "sql_repair_attempted": state.get("sql_repair_attempted", False),
                            "sql_repair_success": state.get("sql_repair_success", False)
                        }
                    }
                elif state.get("chat_response"):
                    # SQL生成失败的解释性响应（不受ENABLE_RESULT_SUMMARY配置影响）
                    state["final_response"] = {
                        "success": True,
                        "response": state["chat_response"],
                        "type": "DATABASE",
                        "sql": state.get("sql"),
                        "query_result": state.get("query_result"),  # 保持内部字段名不变
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
                        "query_result": state.get("query_result"),  # 保持内部字段名不变
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
                        "query_result": query_result,  # 保持内部字段名不变
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
    
    def _route_after_sql_generation(self, state: AgentState) -> Literal["continue_execution", "return_to_user"]:
        """
        SQL生成后的路由决策
        
        根据SQL生成和验证的结果决定后续流向：
        - SQL生成验证成功 → 继续执行SQL
        - SQL生成验证失败 → 直接返回用户提示
        """
        sql_generation_success = state.get("sql_generation_success", False)
        
        print(f"[ROUTE] SQL生成路由: success={sql_generation_success}")
        
        if sql_generation_success:
            return "continue_execution"  # 路由到SQL执行节点
        else:
            return "return_to_user"      # 路由到format_response，结束流程

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
    
    async def process_question(self, question: str, session_id: str = None, context_type: str = None, routing_mode: str = None) -> Dict[str, Any]:
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
            final_state = await workflow.ainvoke(
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
            
            # SQL验证和修复相关状态
            sql_generation_success=False,
            sql_validation_success=False,
            sql_repair_attempted=False,
            sql_repair_success=False,
            validation_error_type=None,
            user_prompt=None,
            
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
    
    # ==================== SQL验证和修复相关方法 ====================
    
    def _is_sql_validation_enabled(self) -> bool:
        """检查是否启用SQL验证"""
        from agent.config import get_nested_config
        return (get_nested_config(self.config, "sql_validation.enable_syntax_validation", False) or 
                get_nested_config(self.config, "sql_validation.enable_forbidden_check", False))

    def _is_auto_repair_enabled(self) -> bool:
        """检查是否启用自动修复"""
        from agent.config import get_nested_config
        return (get_nested_config(self.config, "sql_validation.enable_auto_repair", False) and 
                get_nested_config(self.config, "sql_validation.enable_syntax_validation", False))

    async def _validate_sql_with_custom_priority(self, sql: str) -> Dict[str, Any]:
        """
        按照自定义优先级验证SQL：先禁止词，再语法
        
        Args:
            sql: 要验证的SQL语句
            
        Returns:
            验证结果字典
        """
        try:
            from agent.config import get_nested_config
            
            # 1. 优先检查禁止词（您要求的优先级）
            if get_nested_config(self.config, "sql_validation.enable_forbidden_check", True):
                forbidden_result = self._check_forbidden_keywords(sql)
                if not forbidden_result.get("valid"):
                    return {
                        "valid": False,
                        "error_type": "forbidden_keywords",
                        "error_message": forbidden_result.get("error"),
                        "can_repair": False  # 禁止词错误不能修复
                    }
            
            # 2. 再检查语法（EXPLAIN SQL）
            if get_nested_config(self.config, "sql_validation.enable_syntax_validation", True):
                syntax_result = await self._validate_sql_syntax(sql)
                if not syntax_result.get("valid"):
                    return {
                        "valid": False,
                        "error_type": "syntax_error",
                        "error_message": syntax_result.get("error"),
                        "can_repair": True  # 语法错误可以尝试修复
                    }
            
            return {"valid": True}
            
        except Exception as e:
            return {
                "valid": False,
                "error_type": "validation_exception",
                "error_message": str(e),
                "can_repair": False
            }

    def _check_forbidden_keywords(self, sql: str) -> Dict[str, Any]:
        """检查禁止的SQL关键词"""
        try:
            from agent.config import get_nested_config
            forbidden_operations = get_nested_config(
                self.config, 
                "sql_validation.forbidden_operations", 
                ['UPDATE', 'DELETE', 'DROP', 'ALTER', 'INSERT']
            )
            
            sql_upper = sql.upper().strip()
            
            for operation in forbidden_operations:
                if sql_upper.startswith(operation.upper()):
                    return {
                        "valid": False,
                        "error": f"不允许的操作: {operation}。本系统只支持查询操作(SELECT)。"
                    }
            
            return {"valid": True}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"禁止词检查异常: {str(e)}"
            }

    async def _validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
        """语法验证 - 使用EXPLAIN SQL"""
        try:
            from common.vanna_instance import get_vanna_instance
            import asyncio
            
            vn = get_vanna_instance()
            
            # 构建EXPLAIN查询
            explain_sql = f"EXPLAIN {sql}"
            
            # 异步执行验证
            result = await asyncio.to_thread(vn.run_sql, explain_sql)
            
            if result is not None:
                return {"valid": True}
            else:
                return {
                    "valid": False,
                    "error": "SQL语法验证失败"
                }
                
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }

    async def _attempt_sql_repair_once(self, sql: str, error_message: str) -> Dict[str, Any]:
        """
        使用LLM尝试修复SQL - 只修复一次
        
        Args:
            sql: 原始SQL
            error_message: 错误信息
            
        Returns:
            修复结果字典
        """
        try:
            from common.vanna_instance import get_vanna_instance
            from agent.config import get_nested_config
            import asyncio
            
            vn = get_vanna_instance()
            
            # 构建修复提示词
            repair_prompt = f"""你是一个PostgreSQL SQL专家，请修复以下SQL语句的语法错误。

当前数据库类型: PostgreSQL
错误信息: {error_message}

需要修复的SQL:
{sql}

修复要求:
1. 只修复语法错误和表结构错误
2. 保持SQL的原始业务逻辑不变  
3. 使用PostgreSQL标准语法
4. 确保修复后的SQL语法正确

请直接输出修复后的SQL语句，不要添加其他说明文字。"""

            # 获取超时配置
            timeout = get_nested_config(self.config, "sql_validation.repair_timeout", 60)
            
            # 异步调用LLM修复
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    vn.chat_with_llm,
                    question=repair_prompt,
                    system_prompt="你是一个专业的PostgreSQL SQL专家，专门负责修复SQL语句中的语法错误。"
                ),
                timeout=timeout
            )
            
            if response and response.strip():
                repaired_sql = response.strip()
                
                # 验证修复后的SQL
                validation_result = await self._validate_sql_syntax(repaired_sql)
                
                if validation_result.get("valid"):
                    return {
                        "success": True,
                        "repaired_sql": repaired_sql,
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "repaired_sql": None,
                        "error": f"修复后的SQL仍然无效: {validation_result.get('error')}"
                    }
            else:
                return {
                    "success": False,
                    "repaired_sql": None,
                    "error": "LLM返回空响应"
                }
                
        except asyncio.TimeoutError:
            return {
                "success": False,
                "repaired_sql": None,
                "error": f"修复超时（{get_nested_config(self.config, 'sql_validation.repair_timeout', 60)}秒）"
            }
        except Exception as e:
            return {
                "success": False,
                "repaired_sql": None,
                "error": f"修复异常: {str(e)}"
            }

    # ==================== 原有方法 ====================
    
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

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 从配置获取健康检查参数
            from agent.config import get_nested_config
            test_question = get_nested_config(self.config, "health_check.test_question", "你好")
            enable_full_test = get_nested_config(self.config, "health_check.enable_full_test", True)
            
            if enable_full_test:
                # 完整流程测试
                test_result = await self.process_question(test_question, "health_check")
                
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