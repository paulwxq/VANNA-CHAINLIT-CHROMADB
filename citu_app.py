# 给dataops 对话助手返回结果
from vanna.flask import VannaFlaskApp
from core.vanna_llm_factory import create_vanna_instance
from flask import request, jsonify
import pandas as pd
import common.result as result
from datetime import datetime, timedelta
from common.session_aware_cache import WebSessionAwareMemoryCache
from app_config import API_MAX_RETURN_ROWS, ENABLE_RESULT_SUMMARY
import re
import chainlit as cl
import json
from flask import session  # 添加session导入
from common.redis_conversation_manager import RedisConversationManager  # 添加Redis对话管理器导入

from common.qa_feedback_manager import QAFeedbackManager
from common.result import success_response, bad_request_response, not_found_response, internal_error_response


from common.result import (  # 统一导入所有需要的响应函数
    bad_request_response, service_unavailable_response, 
    agent_success_response, agent_error_response,
    internal_error_response, success_response,
    validation_failed_response
)
from app_config import (  # 添加Redis相关配置导入
    USER_MAX_CONVERSATIONS,
    CONVERSATION_CONTEXT_COUNT,
    DEFAULT_ANONYMOUS_USER,
    ENABLE_QUESTION_ANSWER_CACHE
)

# 设置默认的最大返回行数
DEFAULT_MAX_RETURN_ROWS = 200
MAX_RETURN_ROWS = API_MAX_RETURN_ROWS if API_MAX_RETURN_ROWS is not None else DEFAULT_MAX_RETURN_ROWS

vn = create_vanna_instance()

# 创建带时间戳的缓存
timestamped_cache = WebSessionAwareMemoryCache()

# 实例化 VannaFlaskApp，使用自定义缓存
app = VannaFlaskApp(
    vn,
    cache=timestamped_cache,  # 使用带时间戳的缓存
    title="辞图智能数据问答平台",
    logo = "https://www.citupro.com/img/logo-black-2.png",
    subtitle="让 AI 为你写 SQL",
    chart=False,
    allow_llm_to_see_data=True,
    ask_results_correct=True,
    followup_questions=True,
    debug=True
)

# 创建Redis对话管理器实例
redis_conversation_manager = RedisConversationManager()

# 修改ask接口，支持前端传递session_id
@app.flask_app.route('/api/v0/ask', methods=['POST'])
def ask_full():
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)  # 前端传递的会话ID
    
    if not question:
        from common.result import bad_request_response
        return jsonify(bad_request_response(
            response_text="缺少必需参数：question",
            missing_params=["question"]
        )), 400

    # 如果使用WebSessionAwareMemoryCache
    if hasattr(app.cache, 'generate_id_with_browser_session') and browser_session_id:
        # 这里需要修改vanna的ask方法来支持传递session_id
        # 或者预先调用generate_id来建立会话关联
        conversation_id = app.cache.generate_id_with_browser_session(
            question=question, 
            browser_session_id=browser_session_id
        )

    try:
        sql, df, _ = vn.ask(
            question=question,
            print_results=False,
            visualize=False,
            allow_llm_to_see_data=True
        )

        # 关键：检查是否有LLM解释性文本（无法生成SQL的情况）
        if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
            # 在解释性文本末尾添加提示语
            explanation_message = vn.last_llm_explanation + "请尝试提问其它问题。"
            
            # 使用标准化错误响应
            from common.result import validation_failed_response
            return jsonify(validation_failed_response(
                response_text=explanation_message
            )), 422  # 修改HTTP状态码为422

        # 如果sql为None但没有解释性文本，返回通用错误
        if sql is None:
            from common.result import validation_failed_response
            return jsonify(validation_failed_response(
                response_text="无法生成SQL查询，请检查问题描述或数据表结构"
            )), 422

        # 处理返回数据 - 使用新的query_result结构
        query_result = {
            "rows": [],
            "columns": [],
            "row_count": 0,
            "is_limited": False,
            "total_row_count": 0
        }
        
        summary = None
        
        if isinstance(df, pd.DataFrame):
            query_result["columns"] = list(df.columns)
            if not df.empty:
                total_rows = len(df)
                limited_df = df.head(MAX_RETURN_ROWS)
                query_result["rows"] = limited_df.to_dict(orient="records")
                query_result["row_count"] = len(limited_df)
                query_result["total_row_count"] = total_rows
                query_result["is_limited"] = total_rows > MAX_RETURN_ROWS
                
                # 生成数据摘要（可通过配置控制，仅在有数据时生成）
                if ENABLE_RESULT_SUMMARY:
                    try:
                        summary = vn.generate_summary(question=question, df=df)
                        print(f"[INFO] 成功生成摘要: {summary}")
                    except Exception as e:
                        print(f"[WARNING] 生成摘要失败: {str(e)}")
                        summary = None

        # 构建返回数据
        response_data = {
            "sql": sql,
            "query_result": query_result,
            "conversation_id": conversation_id if 'conversation_id' in locals() else None,
            "session_id": browser_session_id
        }
        
        # 添加摘要（如果启用且生成成功）
        if ENABLE_RESULT_SUMMARY and summary is not None:
            response_data["summary"] = summary
            response_data["response"] = summary  # 同时添加response字段
            
        from common.result import success_response
        return jsonify(success_response(
            response_text="查询执行完成" if summary is None else None,
            data=response_data
        ))
        
    except Exception as e:
        print(f"[ERROR] ask_full执行失败: {str(e)}")
        
        # 即使发生异常，也检查是否有业务层面的解释
        if hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
            # 在解释性文本末尾添加提示语
            explanation_message = vn.last_llm_explanation + "请尝试提问其它问题。"
            
            from common.result import validation_failed_response
            return jsonify(validation_failed_response(
                response_text=explanation_message
            )), 422
        else:
            # 技术错误，使用500错误码
            from common.result import internal_error_response
            return jsonify(internal_error_response(
                response_text="查询处理失败，请稍后重试"
            )), 500

@app.flask_app.route('/api/v0/citu_run_sql', methods=['POST'])
def citu_run_sql():
    req = request.get_json(force=True)
    sql = req.get('sql')
    
    if not sql:
        from common.result import bad_request_response
        return jsonify(bad_request_response(
            response_text="缺少必需参数：sql",
            missing_params=["sql"]
        )), 400
    
    try:
        df = vn.run_sql(sql)
        
        # 处理返回数据 - 使用新的query_result结构
        query_result = {
            "rows": [],
            "columns": [],
            "row_count": 0,
            "is_limited": False,
            "total_row_count": 0
        }
        
        if isinstance(df, pd.DataFrame):
            query_result["columns"] = list(df.columns)
            if not df.empty:
                total_rows = len(df)
                limited_df = df.head(MAX_RETURN_ROWS)
                query_result["rows"] = limited_df.to_dict(orient="records")
                query_result["row_count"] = len(limited_df)
                query_result["total_row_count"] = total_rows
                query_result["is_limited"] = total_rows > MAX_RETURN_ROWS
        
        from common.result import success_response
        return jsonify(success_response(
            response_text=f"SQL执行完成，共返回 {query_result['total_row_count']} 条记录" + 
                         (f"，已限制显示前 {MAX_RETURN_ROWS} 条" if query_result["is_limited"] else ""),
            data={
                "sql": sql,
                "query_result": query_result
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] citu_run_sql执行失败: {str(e)}")
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text=f"SQL执行失败，请检查SQL语句是否正确"
        )), 500

@app.flask_app.route('/api/v0/ask_cached', methods=['POST'])
def ask_cached():
    """
    带缓存功能的智能查询接口
    支持会话管理和结果缓存，提高查询效率
    """
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)
    
    if not question:
        from common.result import bad_request_response
        return jsonify(bad_request_response(
            response_text="缺少必需参数：question",
            missing_params=["question"]
        )), 400

    try:
        # 生成conversation_id
        # 调试：查看generate_id的实际行为
        print(f"[DEBUG] 输入问题: '{question}'")
        conversation_id = app.cache.generate_id(question=question)
        print(f"[DEBUG] 生成的conversation_id: {conversation_id}")
        
        # 再次用相同问题测试
        conversation_id2 = app.cache.generate_id(question=question)
        print(f"[DEBUG] 再次生成的conversation_id: {conversation_id2}")
        print(f"[DEBUG] 两次ID是否相同: {conversation_id == conversation_id2}")
        
        # 检查缓存
        cached_sql = app.cache.get(id=conversation_id, field="sql")
        
        if cached_sql is not None:
            # 缓存命中
            print(f"[CACHE HIT] 使用缓存结果: {conversation_id}")
            sql = cached_sql
            df = app.cache.get(id=conversation_id, field="df")
            summary = app.cache.get(id=conversation_id, field="summary")
        else:
            # 缓存未命中，执行新查询
            print(f"[CACHE MISS] 执行新查询: {conversation_id}")
            
            sql, df, _ = vn.ask(
                question=question,
                print_results=False,
                visualize=False,
                allow_llm_to_see_data=True
            )
            
            # 检查是否有LLM解释性文本（无法生成SQL的情况）
            if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
                # 在解释性文本末尾添加提示语
                explanation_message = vn.last_llm_explanation + "请尝试用其它方式提问。"
                
                from common.result import validation_failed_response
                return jsonify(validation_failed_response(
                    response_text=explanation_message
                )), 422
            
            # 如果sql为None但没有解释性文本，返回通用错误
            if sql is None:
                from common.result import validation_failed_response
                return jsonify(validation_failed_response(
                    response_text="无法生成SQL查询，请检查问题描述或数据表结构"
                )), 422
            
            # 缓存结果
            app.cache.set(id=conversation_id, field="question", value=question)
            app.cache.set(id=conversation_id, field="sql", value=sql)
            app.cache.set(id=conversation_id, field="df", value=df)
            
            # 生成并缓存摘要（可通过配置控制，仅在有数据时生成）
            summary = None
            if ENABLE_RESULT_SUMMARY and isinstance(df, pd.DataFrame) and not df.empty:
                try:
                    summary = vn.generate_summary(question=question, df=df)
                    print(f"[INFO] 成功生成摘要: {summary}")
                except Exception as e:
                    print(f"[WARNING] 生成摘要失败: {str(e)}")
                    summary = None
            
            app.cache.set(id=conversation_id, field="summary", value=summary)

        # 处理返回数据 - 使用新的query_result结构
        query_result = {
            "rows": [],
            "columns": [],
            "row_count": 0,
            "is_limited": False,
            "total_row_count": 0
        }
        
        if isinstance(df, pd.DataFrame):
            query_result["columns"] = list(df.columns)
            if not df.empty:
                total_rows = len(df)
                limited_df = df.head(MAX_RETURN_ROWS)
                query_result["rows"] = limited_df.to_dict(orient="records")
                query_result["row_count"] = len(limited_df)
                query_result["total_row_count"] = total_rows
                query_result["is_limited"] = total_rows > MAX_RETURN_ROWS

        # 构建返回数据
        response_data = {
            "sql": sql,
            "query_result": query_result,
            "conversation_id": conversation_id,
            "session_id": browser_session_id,
            "cached": cached_sql is not None  # 标识是否来自缓存
        }
        
        # 添加摘要（如果启用且生成成功）
        if ENABLE_RESULT_SUMMARY and summary is not None:
            response_data["summary"] = summary
            response_data["response"] = summary  # 同时添加response字段
            
        from common.result import success_response
        return jsonify(success_response(
            response_text="查询执行完成" if summary is None else None,
            data=response_data
        ))
        
    except Exception as e:
        print(f"[ERROR] ask_cached执行失败: {str(e)}")
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="查询处理失败，请稍后重试"
        )), 500
    


@app.flask_app.route('/api/v0/citu_train_question_sql', methods=['POST'])
def citu_train_question_sql():
    """
    训练问题-SQL对接口
    
    此API将接收的question/sql pair写入到training库中，用于训练和改进AI模型。
    支持仅传入SQL或同时传入问题和SQL进行训练。
    
    Args:
        question (str, optional): 用户问题
        sql (str, required): 对应的SQL查询语句
    
    Returns:
        JSON: 包含训练ID和成功消息的响应
    """
    try:
        req = request.get_json(force=True)
        question = req.get('question')
        sql = req.get('sql')
        
        if not sql:
            from common.result import bad_request_response
            return jsonify(bad_request_response(
                response_text="缺少必需参数：sql",
                missing_params=["sql"]
            )), 400
        
        # 正确的调用方式：同时传递question和sql
        if question:
            training_id = vn.train(question=question, sql=sql)
            print(f"训练成功，训练ID为：{training_id}，问题：{question}，SQL：{sql}")
        else:
            training_id = vn.train(sql=sql)
            print(f"训练成功，训练ID为：{training_id}，SQL：{sql}")

        from common.result import success_response
        return jsonify(success_response(
            response_text="问题-SQL对训练成功",
            data={
                "training_id": training_id,
                "message": "Question-SQL pair trained successfully"
            }
        ))
        
    except Exception as e:
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="训练失败，请稍后重试"
        )), 500
    

# ============ LangGraph Agent 集成 ============

# 全局Agent实例（单例模式）
citu_langraph_agent = None

def get_citu_langraph_agent():
    """获取LangGraph Agent实例（懒加载）"""
    global citu_langraph_agent
    if citu_langraph_agent is None:
        try:
            from agent.citu_agent import CituLangGraphAgent
            print("[CITU_APP] 开始创建LangGraph Agent实例...")
            citu_langraph_agent = CituLangGraphAgent()
            print("[CITU_APP] LangGraph Agent实例创建成功")
        except ImportError as e:
            print(f"[CRITICAL] Agent模块导入失败: {str(e)}")
            print("[CRITICAL] 请检查agent模块是否存在以及依赖是否正确安装")
            raise Exception(f"Agent模块导入失败: {str(e)}")
        except Exception as e:
            print(f"[CRITICAL] LangGraph Agent实例创建失败: {str(e)}")
            print(f"[CRITICAL] 错误类型: {type(e).__name__}")
            # 提供更有用的错误信息
            if "config" in str(e).lower():
                print("[CRITICAL] 可能是配置文件问题，请检查配置")
            elif "llm" in str(e).lower():
                print("[CRITICAL] 可能是LLM连接问题，请检查LLM配置")
            elif "tool" in str(e).lower():
                print("[CRITICAL] 可能是工具加载问题，请检查工具模块")
            raise Exception(f"Agent初始化失败: {str(e)}")
    return citu_langraph_agent

@app.flask_app.route('/api/v0/ask_agent', methods=['POST'])
def ask_agent():
    """
    支持对话上下文的ask_agent API - 修正版
    """
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)
    
    # 新增参数解析
    user_id_input = req.get("user_id", None)
    conversation_id_input = req.get("conversation_id", None)
    continue_conversation = req.get("continue_conversation", False)
    
    # 新增：路由模式参数解析和验证
    api_routing_mode = req.get("routing_mode", None)
    VALID_ROUTING_MODES = ["database_direct", "chat_direct", "hybrid", "llm_only"]
    
    if not question:
        return jsonify(bad_request_response(
            response_text="缺少必需参数：question",
            missing_params=["question"]
        )), 400
    
    # 验证routing_mode参数
    if api_routing_mode and api_routing_mode not in VALID_ROUTING_MODES:
        return jsonify(bad_request_response(
            response_text=f"无效的routing_mode参数值: {api_routing_mode}，支持的值: {VALID_ROUTING_MODES}",
            invalid_params=["routing_mode"]
        )), 400

    try:
        # 1. 获取登录用户ID（修正：在函数中获取session信息）
        login_user_id = session.get('user_id') if 'user_id' in session else None
        
        # 2. 智能ID解析（修正：传入登录用户ID）
        user_id = redis_conversation_manager.resolve_user_id(
            user_id_input, browser_session_id, request.remote_addr, login_user_id
        )
        conversation_id, conversation_status = redis_conversation_manager.resolve_conversation_id(
            user_id, conversation_id_input, continue_conversation
        )
        
        # 3. 获取上下文和上下文类型（提前到缓存检查之前）
        context = redis_conversation_manager.get_context(conversation_id)
        
        # 获取上下文类型：从最后一条助手消息的metadata中获取类型
        context_type = None
        if context:
            try:
                # 获取最后一条助手消息的metadata
                messages = redis_conversation_manager.get_messages(conversation_id, limit=10)
                for message in reversed(messages):  # 从最新的开始找
                    if message.get("role") == "assistant":
                        metadata = message.get("metadata", {})
                        context_type = metadata.get("type")
                        if context_type:
                            print(f"[AGENT_API] 检测到上下文类型: {context_type}")
                            break
            except Exception as e:
                print(f"[WARNING] 获取上下文类型失败: {str(e)}")
        
        # 4. 检查缓存（新逻辑：放宽使用条件，严控存储条件）
        cached_answer = redis_conversation_manager.get_cached_answer(question, context)
        if cached_answer:
            print(f"[AGENT_API] 使用缓存答案")
            
            # 确定缓存答案的助手回复内容（使用与非缓存相同的优先级逻辑）
            cached_response_type = cached_answer.get("type", "UNKNOWN")
            if cached_response_type == "DATABASE":
                # DATABASE类型：按优先级选择内容
                if cached_answer.get("response"):
                    # 优先级1：错误或解释性回复（如SQL生成失败）
                    assistant_response = cached_answer.get("response")
                elif cached_answer.get("summary"):
                    # 优先级2：查询成功的摘要
                    assistant_response = cached_answer.get("summary")
                elif cached_answer.get("query_result"):
                    # 优先级3：构造简单描述
                    query_result = cached_answer.get("query_result")
                    row_count = query_result.get("row_count", 0)
                    assistant_response = f"查询执行完成，共返回 {row_count} 条记录。"
                else:
                    # 异常情况
                    assistant_response = "数据库查询已处理。"
            else:
                # CHAT类型：直接使用response
                assistant_response = cached_answer.get("response", "")
            
            # 更新对话历史
            redis_conversation_manager.save_message(conversation_id, "user", question)
            redis_conversation_manager.save_message(
                conversation_id, "assistant", 
                assistant_response,
                metadata={"from_cache": True}
            )
            
            # 添加对话信息到缓存结果
            cached_answer["conversation_id"] = conversation_id
            cached_answer["user_id"] = user_id
            cached_answer["from_cache"] = True
            cached_answer.update(conversation_status)
            
            # 使用agent_success_response返回标准格式
            return jsonify(agent_success_response(
                response_type=cached_answer.get("type", "UNKNOWN"),
                response=cached_answer.get("response", ""),  # 修正：使用response而不是response_text
                sql=cached_answer.get("sql"),
                query_result=cached_answer.get("query_result"),
                summary=cached_answer.get("summary"),
                session_id=browser_session_id,
                execution_path=cached_answer.get("execution_path", []),
                classification_info=cached_answer.get("classification_info", {}),
                conversation_id=conversation_id,
                user_id=user_id,
                is_guest_user=(user_id == DEFAULT_ANONYMOUS_USER),
                context_used=bool(context),
                from_cache=True,
                conversation_status=conversation_status["status"],
                conversation_message=conversation_status["message"],
                requested_conversation_id=conversation_status.get("requested_id")
            ))
        
        # 5. 保存用户消息
        redis_conversation_manager.save_message(conversation_id, "user", question)
        
        # 6. 构建带上下文的问题
        if context:
            enhanced_question = f"\n[CONTEXT]\n{context}\n\n[CURRENT]\n{question}"
            print(f"[AGENT_API] 使用上下文，长度: {len(context)}字符")
        else:
            enhanced_question = question
            print(f"[AGENT_API] 新对话，无上下文")
        
        # 7. 确定最终使用的路由模式（优先级逻辑）
        if api_routing_mode:
            # API传了参数，优先使用
            effective_routing_mode = api_routing_mode
            print(f"[AGENT_API] 使用API指定的路由模式: {effective_routing_mode}")
        else:
            # API没传参数，使用配置文件
            try:
                from app_config import QUESTION_ROUTING_MODE
                effective_routing_mode = QUESTION_ROUTING_MODE
                print(f"[AGENT_API] 使用配置文件路由模式: {effective_routing_mode}")
            except ImportError:
                effective_routing_mode = "hybrid"
                print(f"[AGENT_API] 配置文件读取失败，使用默认路由模式: {effective_routing_mode}")
        
        # 8. 现有Agent处理逻辑（修改为传递路由模式）
        try:
            agent = get_citu_langraph_agent()
        except Exception as e:
            print(f"[CRITICAL] Agent初始化失败: {str(e)}")
            return jsonify(service_unavailable_response(
                response_text="AI服务暂时不可用，请稍后重试",
                can_retry=True
            )), 503
        
        agent_result = agent.process_question(
            question=enhanced_question,  # 使用增强后的问题
            session_id=browser_session_id,
            context_type=context_type,  # 传递上下文类型
            routing_mode=effective_routing_mode  # 新增：传递路由模式
        )
        
        # 8. 处理Agent结果
        if agent_result.get("success", False):
            # 修正：直接从agent_result获取字段，因为它就是final_response
            response_type = agent_result.get("type", "UNKNOWN")
            response_text = agent_result.get("response", "")
            sql = agent_result.get("sql")
            query_result = agent_result.get("query_result")
            summary = agent_result.get("summary")
            execution_path = agent_result.get("execution_path", [])
            classification_info = agent_result.get("classification_info", {})
            
            # 确定助手回复内容的优先级
            if response_type == "DATABASE":
                # DATABASE类型：按优先级选择内容
                if response_text:
                    # 优先级1：错误或解释性回复（如SQL生成失败）
                    assistant_response = response_text
                elif summary:
                    # 优先级2：查询成功的摘要
                    assistant_response = summary
                elif query_result:
                    # 优先级3：构造简单描述
                    row_count = query_result.get("row_count", 0)
                    assistant_response = f"查询执行完成，共返回 {row_count} 条记录。"
                else:
                    # 异常情况
                    assistant_response = "数据库查询已处理。"
            else:
                # CHAT类型：直接使用response
                assistant_response = response_text
            
            # 保存助手回复
            redis_conversation_manager.save_message(
                conversation_id, "assistant", assistant_response,
                metadata={
                    "type": response_type,
                    "sql": sql,
                    "execution_path": execution_path
                }
            )
            
            # 缓存成功的答案（新逻辑：只缓存无上下文的问答）
            # 直接缓存agent_result，它已经包含所有需要的字段
            redis_conversation_manager.cache_answer(question, agent_result, context)
            
            # 使用agent_success_response的正确方式
            return jsonify(agent_success_response(
                response_type=response_type,
                response=response_text,  # 修正：使用response而不是response_text
                sql=sql,
                query_result=query_result,
                summary=summary,
                session_id=browser_session_id,
                execution_path=execution_path,
                classification_info=classification_info,
                conversation_id=conversation_id,
                user_id=user_id,
                is_guest_user=(user_id == DEFAULT_ANONYMOUS_USER),
                context_used=bool(context),
                from_cache=False,
                conversation_status=conversation_status["status"],
                conversation_message=conversation_status["message"],
                requested_conversation_id=conversation_status.get("requested_id"),
                routing_mode_used=effective_routing_mode,  # 新增：实际使用的路由模式
                routing_mode_source="api" if api_routing_mode else "config"  # 新增：路由模式来源
            ))
        else:
            # 错误处理（修正：确保使用现有的错误响应格式）
            error_message = agent_result.get("error", "Agent处理失败")
            error_code = agent_result.get("error_code", 500)
            
            return jsonify(agent_error_response(
                response_text=error_message,
                error_type="agent_processing_failed",
                code=error_code,
                session_id=browser_session_id,
                conversation_id=conversation_id,
                user_id=user_id
            )), error_code
        
    except Exception as e:
        print(f"[ERROR] ask_agent执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询处理失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/agent_health', methods=['GET'])
def agent_health():
    """
    Agent健康检查接口
    
    响应格式:
    {
        "success": true/false,
        "code": 200/503,
        "message": "healthy/degraded/unhealthy",
        "data": {
            "status": "healthy/degraded/unhealthy",
            "test_result": true/false,
            "workflow_compiled": true/false,
            "tools_count": 4,
            "message": "详细信息",
            "timestamp": "2024-01-01T12:00:00",
            "checks": {
                "agent_creation": true/false,
                "tools_import": true/false,
                "llm_connection": true/false,
                "classifier_ready": true/false
            }
        }
    }
    """
    try:
        # 基础健康检查
        health_data = {
            "status": "unknown",
            "test_result": False,
            "workflow_compiled": False,
            "tools_count": 0,
            "message": "",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "agent_creation": False,
                "tools_import": False,
                "llm_connection": False,
                "classifier_ready": False
            }
        }
        
        # 检查1: Agent创建
        try:
            agent = get_citu_langraph_agent()
            health_data["checks"]["agent_creation"] = True
            health_data["workflow_compiled"] = agent.workflow is not None
            health_data["tools_count"] = len(agent.tools) if hasattr(agent, 'tools') else 0
        except Exception as e:
            health_data["message"] = f"Agent创建失败: {str(e)}"
            from common.result import health_error_response
            return jsonify(health_error_response(
                status="unhealthy",
                **health_data
            )), 503
        
        # 检查2: 工具导入
        try:
            from agent.tools import TOOLS
            health_data["checks"]["tools_import"] = len(TOOLS) > 0
        except Exception as e:
            health_data["message"] = f"工具导入失败: {str(e)}"
        
        # 检查3: LLM连接（简单测试）
        try:
            from agent.utils import get_compatible_llm
            llm = get_compatible_llm()
            health_data["checks"]["llm_connection"] = llm is not None
        except Exception as e:
            health_data["message"] = f"LLM连接失败: {str(e)}"
        
        # 检查4: 分类器准备
        try:
            from agent.classifier import QuestionClassifier
            classifier = QuestionClassifier()
            health_data["checks"]["classifier_ready"] = True
        except Exception as e:
            health_data["message"] = f"分类器失败: {str(e)}"
        
        # 检查5: 完整流程测试（可选）
        try:
            if all(health_data["checks"].values()):
                test_result = agent.health_check()
                health_data["test_result"] = test_result.get("status") == "healthy"
                health_data["status"] = test_result.get("status", "unknown")
                health_data["message"] = test_result.get("message", "健康检查完成")
            else:
                health_data["status"] = "degraded"
                health_data["message"] = "部分组件异常"
        except Exception as e:
            health_data["status"] = "degraded"
            health_data["message"] = f"完整测试失败: {str(e)}"
        
        # 根据状态返回相应的HTTP代码 - 使用标准化健康检查响应
        from common.result import health_success_response, health_error_response
        
        if health_data["status"] == "healthy":
            return jsonify(health_success_response(**health_data))
        elif health_data["status"] == "degraded":
            return jsonify(health_error_response(status="degraded", **health_data)), 503
        else:
            return jsonify(health_error_response(status="unhealthy", **health_data)), 503
            
    except Exception as e:
        print(f"[ERROR] 健康检查异常: {str(e)}")
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="健康检查失败，请稍后重试"
        )), 500



# ==================== 日常管理API ====================

@app.flask_app.route('/api/v0/cache_overview', methods=['GET'])
def cache_overview():
    """日常管理：轻量概览 - 合并原cache_inspect的核心功能"""
    try:
        cache = app.cache
        result_data = {
            'overview_summary': {
                'total_conversations': 0,
                'total_sessions': 0,
                'query_time': datetime.now().isoformat()
            },
            'recent_conversations': [],  # 最近的对话
            'session_summary': []       # 会话摘要
        }
        
        if hasattr(cache, 'cache') and isinstance(cache.cache, dict):
            result_data['overview_summary']['total_conversations'] = len(cache.cache)
            
            # 获取会话信息
            if hasattr(cache, 'get_all_sessions'):
                all_sessions = cache.get_all_sessions()
                result_data['overview_summary']['total_sessions'] = len(all_sessions)
                
                # 会话摘要（按最近活动排序）
                session_list = []
                for session_id, session_data in all_sessions.items():
                    session_summary = {
                        'session_id': session_id,
                        'start_time': session_data['start_time'].isoformat(),
                        'conversation_count': session_data.get('conversation_count', 0),
                        'duration_seconds': session_data.get('session_duration_seconds', 0),
                        'last_activity': session_data.get('last_activity', session_data['start_time']).isoformat(),
                        'is_active': (datetime.now() - session_data.get('last_activity', session_data['start_time'])).total_seconds() < 1800  # 30分钟内活跃
                    }
                    session_list.append(session_summary)
                
                # 按最后活动时间排序
                session_list.sort(key=lambda x: x['last_activity'], reverse=True)
                result_data['session_summary'] = session_list
            
            # 最近的对话（最多显示10个）
            conversation_list = []
            for conversation_id, conversation_data in cache.cache.items():
                conversation_start_time = cache.conversation_start_times.get(conversation_id)
                
                conversation_info = {
                    'conversation_id': conversation_id,
                    'conversation_start_time': conversation_start_time.isoformat() if conversation_start_time else None,
                    'session_id': cache.conversation_to_session.get(conversation_id),
                    'has_question': 'question' in conversation_data,
                    'has_sql': 'sql' in conversation_data,
                    'has_data': 'df' in conversation_data and conversation_data['df'] is not None,
                    'question_preview': conversation_data.get('question', '')[:80] + '...' if len(conversation_data.get('question', '')) > 80 else conversation_data.get('question', ''),
                }
                
                # 计算对话持续时间
                if conversation_start_time:
                    duration = datetime.now() - conversation_start_time
                    conversation_info['conversation_duration_seconds'] = duration.total_seconds()
                
                conversation_list.append(conversation_info)
            
            # 按对话开始时间排序，显示最新的10个
            conversation_list.sort(key=lambda x: x['conversation_start_time'] or '', reverse=True)
            result_data['recent_conversations'] = conversation_list[:10]
        
        from common.result import success_response
        return jsonify(success_response(
            response_text="缓存概览查询完成",
            data=result_data
        ))
        
    except Exception as e:
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="获取缓存概览失败，请稍后重试"
        )), 500


@app.flask_app.route('/api/v0/cache_stats', methods=['GET'])
def cache_stats():
    """日常管理：统计信息 - 合并原session_stats和cache_stats功能"""
    try:
        cache = app.cache
        current_time = datetime.now()
        
        stats = {
            'basic_stats': {
                'total_sessions': len(getattr(cache, 'session_info', {})),
                'total_conversations': len(getattr(cache, 'cache', {})),
                'active_sessions': 0,  # 最近30分钟有活动
                'average_conversations_per_session': 0
            },
            'time_distribution': {
                'sessions': {
                    'last_1_hour': 0,
                    'last_6_hours': 0, 
                    'last_24_hours': 0,
                    'last_7_days': 0,
                    'older': 0
                },
                'conversations': {
                    'last_1_hour': 0,
                    'last_6_hours': 0,
                    'last_24_hours': 0, 
                    'last_7_days': 0,
                    'older': 0
                }
            },
            'session_details': [],
            'time_ranges': {
                'oldest_session': None,
                'newest_session': None,
                'oldest_conversation': None,
                'newest_conversation': None
            }
        }
        
        # 会话统计
        if hasattr(cache, 'session_info'):
            session_times = []
            total_conversations = 0
            
            for session_id, session_data in cache.session_info.items():
                start_time = session_data['start_time']
                session_times.append(start_time)
                conversation_count = len(session_data.get('conversations', []))
                total_conversations += conversation_count
                
                # 检查活跃状态
                last_activity = session_data.get('last_activity', session_data['start_time'])
                if (current_time - last_activity).total_seconds() < 1800:
                    stats['basic_stats']['active_sessions'] += 1
                
                # 时间分布统计
                age_hours = (current_time - start_time).total_seconds() / 3600
                if age_hours <= 1:
                    stats['time_distribution']['sessions']['last_1_hour'] += 1
                elif age_hours <= 6:
                    stats['time_distribution']['sessions']['last_6_hours'] += 1
                elif age_hours <= 24:
                    stats['time_distribution']['sessions']['last_24_hours'] += 1
                elif age_hours <= 168:  # 7 days
                    stats['time_distribution']['sessions']['last_7_days'] += 1
                else:
                    stats['time_distribution']['sessions']['older'] += 1
                
                # 会话详细信息
                session_duration = current_time - start_time
                stats['session_details'].append({
                    'session_id': session_id,
                    'start_time': start_time.isoformat(),
                    'last_activity': last_activity.isoformat(),
                    'conversation_count': conversation_count,
                    'duration_seconds': session_duration.total_seconds(),
                    'duration_formatted': str(session_duration),
                    'is_active': (current_time - last_activity).total_seconds() < 1800,
                    'browser_session_id': session_data.get('browser_session_id')
                })
            
            # 计算平均值
            if len(cache.session_info) > 0:
                stats['basic_stats']['average_conversations_per_session'] = total_conversations / len(cache.session_info)
            
            # 时间范围
            if session_times:
                stats['time_ranges']['oldest_session'] = min(session_times).isoformat()
                stats['time_ranges']['newest_session'] = max(session_times).isoformat()
        
        # 对话统计
        if hasattr(cache, 'conversation_start_times'):
            conversation_times = []
            for conv_time in cache.conversation_start_times.values():
                conversation_times.append(conv_time)
                age_hours = (current_time - conv_time).total_seconds() / 3600
                
                if age_hours <= 1:
                    stats['time_distribution']['conversations']['last_1_hour'] += 1
                elif age_hours <= 6:
                    stats['time_distribution']['conversations']['last_6_hours'] += 1
                elif age_hours <= 24:
                    stats['time_distribution']['conversations']['last_24_hours'] += 1
                elif age_hours <= 168:
                    stats['time_distribution']['conversations']['last_7_days'] += 1
                else:
                    stats['time_distribution']['conversations']['older'] += 1
            
            if conversation_times:
                stats['time_ranges']['oldest_conversation'] = min(conversation_times).isoformat()
                stats['time_ranges']['newest_conversation'] = max(conversation_times).isoformat()
        
        # 按最近活动排序会话详情
        stats['session_details'].sort(key=lambda x: x['last_activity'], reverse=True)
        
        from common.result import success_response
        return jsonify(success_response(
            response_text="缓存统计信息查询完成",
            data=stats
        ))
        
    except Exception as e:
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="获取缓存统计失败，请稍后重试"
        )), 500


# ==================== 高级功能API ====================

@app.flask_app.route('/api/v0/cache_export', methods=['GET'])
def cache_export():
    """高级功能：完整导出 - 保持原cache_raw_export的完整功能"""
    try:
        cache = app.cache
        
        # 验证缓存的实际结构
        if not hasattr(cache, 'cache'):
            from common.result import internal_error_response
            return jsonify(internal_error_response(
                response_text="缓存对象结构异常，请联系系统管理员"
            )), 500
        
        if not isinstance(cache.cache, dict):
            from common.result import internal_error_response
            return jsonify(internal_error_response(
                response_text="缓存数据类型异常，请联系系统管理员"
            )), 500
        
        # 定义JSON序列化辅助函数
        def make_json_serializable(obj):
            """将对象转换为JSON可序列化的格式"""
            if obj is None:
                return None
            elif isinstance(obj, (str, int, float, bool)):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [make_json_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                return {str(k): make_json_serializable(v) for k, v in obj.items()}
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            elif hasattr(obj, 'item'):  # numpy scalars
                return obj.item()
            elif hasattr(obj, 'tolist'):  # numpy arrays
                return obj.tolist()
            elif hasattr(obj, '__dict__'):  # pandas dtypes and other objects
                return str(obj)
            else:
                return str(obj)
        
        # 获取完整的原始缓存数据
        raw_cache = cache.cache
        
        # 获取会话和对话时间信息
        conversation_times = getattr(cache, 'conversation_start_times', {})
        session_info = getattr(cache, 'session_info', {})
        conversation_to_session = getattr(cache, 'conversation_to_session', {})
        
        export_data = {
            'export_metadata': {
                'export_time': datetime.now().isoformat(),
                'total_conversations': len(raw_cache),
                'total_sessions': len(session_info),
                'cache_type': type(cache).__name__,
                'cache_object_info': str(cache),
                'has_session_times': bool(session_info),
                'has_conversation_times': bool(conversation_times)
            },
            'session_info': {
                session_id: {
                    'start_time': session_data['start_time'].isoformat(),
                    'last_activity': session_data.get('last_activity', session_data['start_time']).isoformat(),
                    'conversations': session_data['conversations'],
                    'conversation_count': len(session_data['conversations']),
                    'browser_session_id': session_data.get('browser_session_id'),
                    'user_info': session_data.get('user_info', {})
                }
                for session_id, session_data in session_info.items()
            },
            'conversation_times': {
                conversation_id: start_time.isoformat() 
                for conversation_id, start_time in conversation_times.items()
            },
            'conversation_to_session_mapping': conversation_to_session,
            'conversations': {}
        }
        
        # 处理每个对话的完整数据
        for conversation_id, conversation_data in raw_cache.items():
            # 获取时间信息
            conversation_start_time = conversation_times.get(conversation_id)
            session_id = conversation_to_session.get(conversation_id)
            session_start_time = None
            if session_id and session_id in session_info:
                session_start_time = session_info[session_id]['start_time']
            
            processed_conversation = {
                'conversation_id': conversation_id,
                'conversation_start_time': conversation_start_time.isoformat() if conversation_start_time else None,
                'session_id': session_id,
                'session_start_time': session_start_time.isoformat() if session_start_time else None,
                'field_count': len(conversation_data),
                'fields': {}
            }
            
            # 添加时间计算
            if conversation_start_time:
                conversation_duration = datetime.now() - conversation_start_time
                processed_conversation['conversation_duration_seconds'] = conversation_duration.total_seconds()
                processed_conversation['conversation_duration_formatted'] = str(conversation_duration)
            
            if session_start_time:
                session_duration = datetime.now() - session_start_time
                processed_conversation['session_duration_seconds'] = session_duration.total_seconds()
                processed_conversation['session_duration_formatted'] = str(session_duration)
            
            # 处理每个字段，确保JSON序列化安全
            for field_name, field_value in conversation_data.items():
                field_info = {
                    'field_name': field_name,
                    'data_type': type(field_value).__name__,
                    'is_none': field_value is None
                }
                
                try:
                    if field_value is None:
                        field_info['value'] = None
                        
                    elif field_name in ['conversation_start_time', 'session_start_time']:
                        # 处理时间字段
                        field_info['content'] = make_json_serializable(field_value)
                        
                    elif field_name == 'df' and field_value is not None:
                        # DataFrame的安全处理
                        if hasattr(field_value, 'to_dict'):
                            # 安全地处理dtypes
                            try:
                                dtypes_dict = {}
                                for col, dtype in field_value.dtypes.items():
                                    dtypes_dict[col] = str(dtype)
                            except Exception:
                                dtypes_dict = {"error": "无法序列化dtypes"}
                            
                            # 安全地处理内存使用
                            try:
                                memory_usage = field_value.memory_usage(deep=True)
                                memory_dict = {}
                                for idx, usage in memory_usage.items():
                                    memory_dict[str(idx)] = int(usage) if hasattr(usage, 'item') else int(usage)
                            except Exception:
                                memory_dict = {"error": "无法获取内存使用信息"}
                            
                            field_info.update({
                                'dataframe_info': {
                                    'shape': list(field_value.shape),
                                    'columns': list(field_value.columns),
                                    'dtypes': dtypes_dict,
                                    'index_info': {
                                        'type': type(field_value.index).__name__,
                                        'length': len(field_value.index)
                                    }
                                },
                                'data': make_json_serializable(field_value.to_dict('records')),
                                'memory_usage': memory_dict
                            })
                        else:
                            field_info['value'] = str(field_value)
                            field_info['note'] = 'not_standard_dataframe'
                    
                    elif field_name == 'fig_json':
                        # 图表JSON数据处理
                        if isinstance(field_value, str):
                            try:
                                import json
                                parsed_fig = json.loads(field_value)
                                field_info.update({
                                    'json_valid': True,
                                    'json_size_bytes': len(field_value),
                                    'plotly_structure': {
                                        'has_data': 'data' in parsed_fig,
                                        'has_layout': 'layout' in parsed_fig,
                                        'data_traces_count': len(parsed_fig.get('data', [])),
                                    },
                                    'raw_json': field_value
                                })
                            except json.JSONDecodeError:
                                field_info.update({
                                    'json_valid': False,
                                    'raw_content': str(field_value)
                                })
                        else:
                            field_info['value'] = make_json_serializable(field_value)
                    
                    elif field_name == 'followup_questions':
                        # 后续问题列表
                        field_info.update({
                            'content': make_json_serializable(field_value)
                        })
                    
                    elif field_name in ['question', 'sql', 'summary']:
                        # 文本字段
                        if isinstance(field_value, str):
                            field_info.update({
                                'text_length': len(field_value),
                                'content': field_value
                            })
                        else:
                            field_info['value'] = make_json_serializable(field_value)
                    
                    else:
                        # 未知字段的安全处理
                        field_info['content'] = make_json_serializable(field_value)
                
                except Exception as e:
                    field_info.update({
                        'processing_error': str(e),
                        'fallback_value': str(field_value)[:500] + '...' if len(str(field_value)) > 500 else str(field_value)
                    })
                
                processed_conversation['fields'][field_name] = field_info
            
            export_data['conversations'][conversation_id] = processed_conversation
        
        # 添加缓存统计信息
        field_frequency = {}
        data_types_found = set()
        total_dataframes = 0
        total_questions = 0
        
        for conv_data in export_data['conversations'].values():
            for field_name, field_info in conv_data['fields'].items():
                field_frequency[field_name] = field_frequency.get(field_name, 0) + 1
                data_types_found.add(field_info['data_type'])
                
                if field_name == 'df' and not field_info['is_none']:
                    total_dataframes += 1
                if field_name == 'question' and not field_info['is_none']:
                    total_questions += 1
        
        export_data['cache_statistics'] = {
            'field_frequency': field_frequency,
            'data_types_found': list(data_types_found),
            'total_dataframes': total_dataframes,
            'total_questions': total_questions,
            'has_session_timing': 'session_start_time' in field_frequency,
            'has_conversation_timing': 'conversation_start_time' in field_frequency
        }
        
        from common.result import success_response
        return jsonify(success_response(
            response_text="缓存数据导出完成",
            data=export_data
        ))
        
    except Exception as e:
        import traceback
        error_details = {
            'error_message': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc()
        }
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="导出缓存失败，请稍后重试"
        )), 500


# ==================== 清理功能API ====================

@app.flask_app.route('/api/v0/cache_preview_cleanup', methods=['POST'])
def cache_preview_cleanup():
    """清理功能：预览删除操作 - 保持原功能"""
    try:
        req = request.get_json(force=True)
        
        # 时间条件 - 支持三种方式
        older_than_hours = req.get('older_than_hours')
        older_than_days = req.get('older_than_days') 
        before_timestamp = req.get('before_timestamp')  # YYYY-MM-DD HH:MM:SS 格式
        
        cache = app.cache
        
        # 计算截止时间
        cutoff_time = None
        time_condition = None
        
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            time_condition = f"older_than_hours: {older_than_hours}"
        elif older_than_days:
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            time_condition = f"older_than_days: {older_than_days}"
        elif before_timestamp:
            try:
                # 支持 YYYY-MM-DD HH:MM:SS 格式
                cutoff_time = datetime.strptime(before_timestamp, '%Y-%m-%d %H:%M:%S')
                time_condition = f"before_timestamp: {before_timestamp}"
            except ValueError:
                from common.result import validation_failed_response
                return jsonify(validation_failed_response(
                    response_text="before_timestamp格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式"
                )), 422
        else:
            from common.result import bad_request_response
            return jsonify(bad_request_response(
                response_text="必须提供时间条件：older_than_hours, older_than_days 或 before_timestamp (YYYY-MM-DD HH:MM:SS)",
                missing_params=["older_than_hours", "older_than_days", "before_timestamp"]
            )), 400
        
        preview = {
            'time_condition': time_condition,
            'cutoff_time': cutoff_time.isoformat(),
            'will_be_removed': {
                'sessions': []
            },
            'will_be_kept': {
                'sessions_count': 0,
                'conversations_count': 0
            },
            'summary': {
                'sessions_to_remove': 0,
                'conversations_to_remove': 0,
                'sessions_to_keep': 0,
                'conversations_to_keep': 0
            }
        }
        
        # 预览按session删除
        sessions_to_remove_count = 0
        conversations_to_remove_count = 0
        
        for session_id, session_data in cache.session_info.items():
            session_preview = {
                'session_id': session_id,
                'start_time': session_data['start_time'].isoformat(),
                'conversation_count': len(session_data['conversations']),
                'conversations': []
            }
            
            # 添加conversation详情
            for conv_id in session_data['conversations']:
                if conv_id in cache.cache:
                    conv_data = cache.cache[conv_id]
                    session_preview['conversations'].append({
                        'conversation_id': conv_id,
                        'question': conv_data.get('question', '')[:50] + '...' if conv_data.get('question') else '',
                        'start_time': cache.conversation_start_times.get(conv_id, '').isoformat() if cache.conversation_start_times.get(conv_id) else ''
                    })
            
            if session_data['start_time'] < cutoff_time:
                preview['will_be_removed']['sessions'].append(session_preview)
                sessions_to_remove_count += 1
                conversations_to_remove_count += len(session_data['conversations'])
            else:
                preview['will_be_kept']['sessions_count'] += 1
                preview['will_be_kept']['conversations_count'] += len(session_data['conversations'])
        
        # 更新摘要统计
        preview['summary'] = {
            'sessions_to_remove': sessions_to_remove_count,
            'conversations_to_remove': conversations_to_remove_count,
            'sessions_to_keep': preview['will_be_kept']['sessions_count'],
            'conversations_to_keep': preview['will_be_kept']['conversations_count']
        }
        
        from common.result import success_response
        return jsonify(success_response(
            response_text=f"清理预览完成，将删除 {sessions_to_remove_count} 个会话和 {conversations_to_remove_count} 个对话",
            data=preview
        ))
        
    except Exception as e:
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="预览清理操作失败，请稍后重试"
        )), 500


@app.flask_app.route('/api/v0/cache_cleanup', methods=['POST'])
def cache_cleanup():
    """清理功能：实际删除缓存 - 保持原功能"""
    try:
        req = request.get_json(force=True)
        
        # 时间条件 - 支持三种方式
        older_than_hours = req.get('older_than_hours')
        older_than_days = req.get('older_than_days') 
        before_timestamp = req.get('before_timestamp')  # YYYY-MM-DD HH:MM:SS 格式
        
        cache = app.cache
        
        if not hasattr(cache, 'session_info'):
            from common.result import service_unavailable_response
            return jsonify(service_unavailable_response(
                response_text="缓存不支持会话功能"
            )), 503
        
        # 计算截止时间
        cutoff_time = None
        time_condition = None
        
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            time_condition = f"older_than_hours: {older_than_hours}"
        elif older_than_days:
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            time_condition = f"older_than_days: {older_than_days}"
        elif before_timestamp:
            try:
                # 支持 YYYY-MM-DD HH:MM:SS 格式
                cutoff_time = datetime.strptime(before_timestamp, '%Y-%m-%d %H:%M:%S')
                time_condition = f"before_timestamp: {before_timestamp}"
            except ValueError:
                from common.result import validation_failed_response
                return jsonify(validation_failed_response(
                    response_text="before_timestamp格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式"
                )), 422
        else:
            from common.result import bad_request_response
            return jsonify(bad_request_response(
                response_text="必须提供时间条件：older_than_hours, older_than_days 或 before_timestamp (YYYY-MM-DD HH:MM:SS)",
                missing_params=["older_than_hours", "older_than_days", "before_timestamp"]
            )), 400
        
        cleanup_stats = {
            'time_condition': time_condition,
            'cutoff_time': cutoff_time.isoformat(),
            'sessions_removed': 0,
            'conversations_removed': 0,
            'sessions_kept': 0,
            'conversations_kept': 0,
            'removed_session_ids': [],
            'removed_conversation_ids': []
        }
        
        # 按session删除
        sessions_to_remove = []
        
        for session_id, session_data in cache.session_info.items():
            if session_data['start_time'] < cutoff_time:
                sessions_to_remove.append(session_id)
        
        # 删除符合条件的sessions及其所有conversations
        for session_id in sessions_to_remove:
            session_data = cache.session_info[session_id]
            conversations_in_session = session_data['conversations'].copy()
            
            # 删除session中的所有conversations
            for conv_id in conversations_in_session:
                if conv_id in cache.cache:
                    del cache.cache[conv_id]
                    cleanup_stats['conversations_removed'] += 1
                    cleanup_stats['removed_conversation_ids'].append(conv_id)
                
                # 清理conversation相关的时间记录
                if hasattr(cache, 'conversation_start_times') and conv_id in cache.conversation_start_times:
                    del cache.conversation_start_times[conv_id]
                
                if hasattr(cache, 'conversation_to_session') and conv_id in cache.conversation_to_session:
                    del cache.conversation_to_session[conv_id]
            
            # 删除session记录
            del cache.session_info[session_id]
            cleanup_stats['sessions_removed'] += 1
            cleanup_stats['removed_session_ids'].append(session_id)
        
        # 统计保留的sessions和conversations
        cleanup_stats['sessions_kept'] = len(cache.session_info)
        cleanup_stats['conversations_kept'] = len(cache.cache)
        
        from common.result import success_response
        return jsonify(success_response(
            response_text=f"缓存清理完成，删除了 {cleanup_stats['sessions_removed']} 个会话和 {cleanup_stats['conversations_removed']} 个对话",
            data=cleanup_stats
        ))
        
    except Exception as e:
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="缓存清理失败，请稍后重试"
        )), 500
    

@app.flask_app.route('/api/v0/training_error_question_sql', methods=['POST'])
def training_error_question_sql():
    """
    存储错误的question-sql对到error_sql集合中
    
    此API将接收的错误question/sql pair写入到error_sql集合中，用于记录和分析错误的SQL查询。
    
    Args:
        question (str, required): 用户问题
        sql (str, required): 对应的错误SQL查询语句
    
    Returns:
        JSON: 包含训练ID和成功消息的响应
    """
    try:
        data = request.get_json()
        question = data.get('question')
        sql = data.get('sql')
        
        print(f"[DEBUG] 接收到错误SQL训练请求: question={question}, sql={sql}")
        
        if not question or not sql:
            from common.result import bad_request_response
            missing_params = []
            if not question:
                missing_params.append("question")
            if not sql:
                missing_params.append("sql")
            
            return jsonify(bad_request_response(
                response_text="question和sql参数都是必需的",
                missing_params=missing_params
            )), 400
        
        # 使用vn实例的train_error_sql方法存储错误SQL
        id = vn.train_error_sql(question=question, sql=sql)
        
        print(f"[INFO] 成功存储错误SQL，ID: {id}")
        
        from common.result import success_response
        return jsonify(success_response(
            response_text="错误SQL对已成功存储",
            data={
                "id": id,
                "message": "错误SQL对已成功存储到error_sql集合"
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] 存储错误SQL失败: {str(e)}")
        from common.result import internal_error_response
        return jsonify(internal_error_response(
            response_text="存储错误SQL失败，请稍后重试"
        )), 500



# ==================== Redis对话管理API ====================

@app.flask_app.route('/api/v0/user/<user_id>/conversations', methods=['GET'])
def get_user_conversations(user_id: str):
    """获取用户的对话列表（按时间倒序）"""
    try:
        limit = request.args.get('limit', USER_MAX_CONVERSATIONS, type=int)
        conversations = redis_conversation_manager.get_conversations(user_id, limit)
        
        return jsonify(success_response(
            response_text="获取用户对话列表成功",
            data={
                "user_id": user_id,
                "conversations": conversations,
                "total_count": len(conversations)
            }
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(
            response_text="获取对话列表失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/conversation/<conversation_id>/messages', methods=['GET'])
def get_conversation_messages(conversation_id: str):
    """获取特定对话的消息历史"""
    try:
        limit = request.args.get('limit', type=int)  # 可选参数
        messages = redis_conversation_manager.get_conversation_messages(conversation_id, limit)
        meta = redis_conversation_manager.get_conversation_meta(conversation_id)
        
        return jsonify(success_response(
            response_text="获取对话消息成功",
            data={
                "conversation_id": conversation_id,
                "conversation_meta": meta,
                "messages": messages,
                "message_count": len(messages)
            }
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(
            response_text="获取对话消息失败"
        )), 500

@app.flask_app.route('/api/v0/conversation/<conversation_id>/context', methods=['GET'])  
def get_conversation_context(conversation_id: str):
    """获取对话上下文（格式化用于LLM）"""
    try:
        count = request.args.get('count', CONVERSATION_CONTEXT_COUNT, type=int)
        context = redis_conversation_manager.get_context(conversation_id, count)
        
        return jsonify(success_response(
            response_text="获取对话上下文成功",
            data={
                "conversation_id": conversation_id,
                "context": context,
                "context_message_count": count
            }
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(
            response_text="获取对话上下文失败"
        )), 500

@app.flask_app.route('/api/v0/conversation_stats', methods=['GET'])
def conversation_stats():
    """获取对话系统统计信息"""
    try:
        stats = redis_conversation_manager.get_stats()
        
        return jsonify(success_response(
            response_text="获取统计信息成功",
            data=stats
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(
            response_text="获取统计信息失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/conversation_cleanup', methods=['POST'])
def conversation_cleanup():
    """手动清理过期对话"""
    try:
        redis_conversation_manager.cleanup_expired_conversations()
        
        return jsonify(success_response(
            response_text="对话清理完成"
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(
            response_text="对话清理失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/user/<user_id>/conversations/full', methods=['GET'])
def get_user_conversations_with_messages(user_id: str):
    """
    获取用户的完整对话数据（包含所有消息）
    一次性返回用户的所有对话和每个对话下的消息历史
    
    Args:
        user_id: 用户ID（路径参数）
        conversation_limit: 对话数量限制（查询参数，可选，不传则返回所有对话）
        message_limit: 每个对话的消息数限制（查询参数，可选，不传则返回所有消息）
    
    Returns:
        包含用户所有对话和消息的完整数据
    """
    try:
        # 获取可选参数，不传递时使用None（返回所有记录）
        conversation_limit = request.args.get('conversation_limit', type=int)
        message_limit = request.args.get('message_limit', type=int)
        
        # 获取用户的对话列表
        conversations = redis_conversation_manager.get_conversations(user_id, conversation_limit)
        
        # 为每个对话获取消息历史
        full_conversations = []
        total_messages = 0
        
        for conversation in conversations:
            conversation_id = conversation['conversation_id']
            
            # 获取对话消息
            messages = redis_conversation_manager.get_conversation_messages(
                conversation_id, message_limit
            )
            
            # 获取对话元数据
            meta = redis_conversation_manager.get_conversation_meta(conversation_id)
            
            # 组合完整数据
            full_conversation = {
                **conversation,  # 基础对话信息
                'meta': meta,    # 对话元数据
                'messages': messages,  # 消息列表
                'message_count': len(messages)
            }
            
            full_conversations.append(full_conversation)
            total_messages += len(messages)
        
        return jsonify(success_response(
            response_text="获取用户完整对话数据成功",
            data={
                "user_id": user_id,
                "conversations": full_conversations,
                "total_conversations": len(full_conversations),
                "total_messages": total_messages,
                "conversation_limit_applied": conversation_limit,
                "message_limit_applied": message_limit,
                "query_time": datetime.now().isoformat()
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] 获取用户完整对话数据失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取用户对话数据失败，请稍后重试"
        )), 500


# ==================== Embedding缓存管理接口 ====================

@app.flask_app.route('/api/v0/embedding_cache_stats', methods=['GET'])
def embedding_cache_stats():
    """获取embedding缓存统计信息"""
    try:
        from common.embedding_cache_manager import get_embedding_cache_manager
        
        cache_manager = get_embedding_cache_manager()
        stats = cache_manager.get_cache_stats()
        
        return jsonify(success_response(
            response_text="获取embedding缓存统计成功",
            data=stats
        ))
        
    except Exception as e:
        print(f"[ERROR] 获取embedding缓存统计失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取embedding缓存统计失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/embedding_cache_cleanup', methods=['POST'])
def embedding_cache_cleanup():
    """清空所有embedding缓存"""
    try:
        from common.embedding_cache_manager import get_embedding_cache_manager
        
        cache_manager = get_embedding_cache_manager()
        
        if not cache_manager.is_available():
            return jsonify(internal_error_response(
                response_text="Embedding缓存功能未启用或不可用"
            )), 400
        
        success = cache_manager.clear_all_cache()
        
        if success:
            return jsonify(success_response(
                response_text="所有embedding缓存已清空",
                data={"cleared": True}
            ))
        else:
            return jsonify(internal_error_response(
                response_text="清空embedding缓存失败"
            )), 500
        
    except Exception as e:
        print(f"[ERROR] 清空embedding缓存失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="清空embedding缓存失败，请稍后重试"
        )), 500


# ==================== QA反馈系统接口 ====================
# 全局反馈管理器实例
qa_feedback_manager = None

def get_qa_feedback_manager():
    """获取QA反馈管理器实例（懒加载）- 复用Vanna连接版本"""
    global qa_feedback_manager
    if qa_feedback_manager is None:
        try:
            # 优先尝试复用vanna连接
            vanna_instance = None
            try:
                # 尝试获取现有的vanna实例
                if 'get_citu_langraph_agent' in globals():
                    agent = get_citu_langraph_agent()
                    if hasattr(agent, 'vn'):
                        vanna_instance = agent.vn
                elif 'vn' in globals():
                    vanna_instance = vn
                else:
                    print("[INFO] 未找到可用的vanna实例，将创建新的数据库连接")
            except Exception as e:
                print(f"[INFO] 获取vanna实例失败: {e}，将创建新的数据库连接")
                vanna_instance = None
            
            qa_feedback_manager = QAFeedbackManager(vanna_instance=vanna_instance)
            print("[CITU_APP] QA反馈管理器实例创建成功")
        except Exception as e:
            print(f"[CRITICAL] QA反馈管理器创建失败: {str(e)}")
            raise Exception(f"QA反馈管理器初始化失败: {str(e)}")
    return qa_feedback_manager


@app.flask_app.route('/api/v0/qa_feedback/query', methods=['POST'])
def qa_feedback_query():
    """
    查询反馈记录API
    支持分页、筛选和排序功能
    """
    try:
        req = request.get_json(force=True)
        
        # 解析参数，设置默认值
        page = req.get('page', 1)
        page_size = req.get('page_size', 20)
        is_thumb_up = req.get('is_thumb_up')
        create_time_start = req.get('create_time_start')
        create_time_end = req.get('create_time_end')
        is_in_training_data = req.get('is_in_training_data')
        sort_by = req.get('sort_by', 'create_time')
        sort_order = req.get('sort_order', 'desc')
        
        # 参数验证
        if page < 1:
            return jsonify(bad_request_response(
                response_text="页码必须大于0",
                invalid_params=["page"]
            )), 400
        
        if page_size < 1 or page_size > 100:
            return jsonify(bad_request_response(
                response_text="每页大小必须在1-100之间",
                invalid_params=["page_size"]
            )), 400
        
        # 获取反馈管理器并查询
        manager = get_qa_feedback_manager()
        records, total = manager.query_feedback(
            page=page,
            page_size=page_size,
            is_thumb_up=is_thumb_up,
            create_time_start=create_time_start,
            create_time_end=create_time_end,
            is_in_training_data=is_in_training_data,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 计算分页信息
        total_pages = (total + page_size - 1) // page_size
        
        return jsonify(success_response(
            response_text=f"查询成功，共找到 {total} 条记录",
            data={
                "records": records,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] qa_feedback_query执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询反馈记录失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_feedback/delete/<int:feedback_id>', methods=['DELETE'])
def qa_feedback_delete(feedback_id):
    """
    删除反馈记录API
    """
    try:
        manager = get_qa_feedback_manager()
        success = manager.delete_feedback(feedback_id)
        
        if success:
            return jsonify(success_response(
                response_text=f"反馈记录删除成功",
                data={"deleted_id": feedback_id}
            ))
        else:
            return jsonify(not_found_response(
                response_text=f"反馈记录不存在 (ID: {feedback_id})"
            )), 404
            
    except Exception as e:
        print(f"[ERROR] qa_feedback_delete执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除反馈记录失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_feedback/update/<int:feedback_id>', methods=['PUT'])
def qa_feedback_update(feedback_id):
    """
    更新反馈记录API
    """
    try:
        req = request.get_json(force=True)
        
        # 提取允许更新的字段
        allowed_fields = ['question', 'sql', 'is_thumb_up', 'user_id', 'is_in_training_data']
        update_data = {}
        
        for field in allowed_fields:
            if field in req:
                update_data[field] = req[field]
        
        if not update_data:
            return jsonify(bad_request_response(
                response_text="没有提供有效的更新字段",
                missing_params=allowed_fields
            )), 400
        
        manager = get_qa_feedback_manager()
        success = manager.update_feedback(feedback_id, **update_data)
        
        if success:
            return jsonify(success_response(
                response_text="反馈记录更新成功",
                data={
                    "updated_id": feedback_id,
                    "updated_fields": list(update_data.keys())
                }
            ))
        else:
            return jsonify(not_found_response(
                response_text=f"反馈记录不存在或无变化 (ID: {feedback_id})"
            )), 404
            
    except Exception as e:
        print(f"[ERROR] qa_feedback_update执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="更新反馈记录失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_feedback/add_to_training', methods=['POST'])
def qa_feedback_add_to_training():
    """
    将反馈记录添加到训练数据集API
    支持混合批量处理：正向反馈加入SQL训练集，负向反馈加入error_sql训练集
    """
    try:
        req = request.get_json(force=True)
        feedback_ids = req.get('feedback_ids', [])
        
        if not feedback_ids or not isinstance(feedback_ids, list):
            return jsonify(bad_request_response(
                response_text="缺少有效的反馈ID列表",
                missing_params=["feedback_ids"]
            )), 400
        
        manager = get_qa_feedback_manager()
        
        # 获取反馈记录
        records = manager.get_feedback_by_ids(feedback_ids)
        
        if not records:
            return jsonify(not_found_response(
                response_text="未找到任何有效的反馈记录"
            )), 404
        
        # 分别处理正向和负向反馈
        positive_count = 0  # 正向训练计数
        negative_count = 0  # 负向训练计数
        already_trained_count = 0  # 已训练计数
        error_count = 0  # 错误计数
        
        successfully_trained_ids = []  # 成功训练的ID列表
        
        for record in records:
            try:
                # 检查是否已经在训练数据中
                if record['is_in_training_data']:
                    already_trained_count += 1
                    continue
                
                if record['is_thumb_up']:
                    # 正向反馈 - 加入标准SQL训练集
                    training_id = vn.train(
                        question=record['question'], 
                        sql=record['sql']
                    )
                    positive_count += 1
                    print(f"[TRAINING] 正向训练成功 - ID: {record['id']}, TrainingID: {training_id}")
                else:
                    # 负向反馈 - 加入错误SQL训练集
                    training_id = vn.train_error_sql(
                        question=record['question'], 
                        sql=record['sql']
                    )
                    negative_count += 1
                    print(f"[TRAINING] 负向训练成功 - ID: {record['id']}, TrainingID: {training_id}")
                
                successfully_trained_ids.append(record['id'])
                
            except Exception as e:
                print(f"[ERROR] 训练失败 - 反馈ID: {record['id']}, 错误: {e}")
                error_count += 1
        
        # 更新训练状态
        if successfully_trained_ids:
            updated_count = manager.mark_training_status(successfully_trained_ids, True)
            print(f"[TRAINING] 批量更新训练状态完成，影响 {updated_count} 条记录")
        
        # 构建响应
        total_processed = positive_count + negative_count + already_trained_count + error_count
        
        return jsonify(success_response(
            response_text=f"训练数据添加完成，成功处理 {positive_count + negative_count} 条记录",
            data={
                "summary": {
                    "total_requested": len(feedback_ids),
                    "total_processed": total_processed,
                    "positive_trained": positive_count,
                    "negative_trained": negative_count,
                    "already_trained": already_trained_count,
                    "errors": error_count
                },
                "successfully_trained_ids": successfully_trained_ids,
                "training_details": {
                    "sql_training_count": positive_count,
                    "error_sql_training_count": negative_count
                }
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] qa_feedback_add_to_training执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="添加训练数据失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_feedback/add', methods=['POST'])
def qa_feedback_add():
    """
    添加反馈记录API
    用于前端直接创建反馈记录
    """
    try:
        req = request.get_json(force=True)
        question = req.get('question')
        sql = req.get('sql')
        is_thumb_up = req.get('is_thumb_up')
        user_id = req.get('user_id', 'guest')
        
        # 参数验证
        if not question:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：question",
                missing_params=["question"]
            )), 400
        
        if not sql:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：sql",
                missing_params=["sql"]
            )), 400
        
        if is_thumb_up is None:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：is_thumb_up",
                missing_params=["is_thumb_up"]
            )), 400
        
        manager = get_qa_feedback_manager()
        feedback_id = manager.add_feedback(
            question=question,
            sql=sql,
            is_thumb_up=bool(is_thumb_up),
            user_id=user_id
        )
        
        return jsonify(success_response(
            response_text="反馈记录创建成功",
            data={
                "feedback_id": feedback_id,
                "message": "Feedback record created successfully"
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] qa_feedback_add执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建反馈记录失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_feedback/stats', methods=['GET'])
def qa_feedback_stats():
    """
    反馈统计API
    返回反馈数据的统计信息
    """
    try:
        manager = get_qa_feedback_manager()
        
        # 查询各种统计数据
        all_records, total_count = manager.query_feedback(page=1, page_size=1)
        positive_records, positive_count = manager.query_feedback(page=1, page_size=1, is_thumb_up=True)
        negative_records, negative_count = manager.query_feedback(page=1, page_size=1, is_thumb_up=False)
        trained_records, trained_count = manager.query_feedback(page=1, page_size=1, is_in_training_data=True)
        untrained_records, untrained_count = manager.query_feedback(page=1, page_size=1, is_in_training_data=False)
        
        return jsonify(success_response(
            response_text="统计信息获取成功",
            data={
                "total_feedback": total_count,
                "positive_feedback": positive_count,
                "negative_feedback": negative_count,
                "trained_feedback": trained_count,
                "untrained_feedback": untrained_count,
                "positive_rate": round(positive_count / max(total_count, 1) * 100, 2),
                "training_rate": round(trained_count / max(total_count, 1) * 100, 2)
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] qa_feedback_stats执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取统计信息失败，请稍后重试"
        )), 500


# ==================== 问答缓存管理接口 ====================

@app.flask_app.route('/api/v0/qa_cache_stats', methods=['GET'])
def qa_cache_stats():
    """获取问答缓存统计信息"""
    try:
        stats = redis_conversation_manager.get_qa_cache_stats()
        
        return jsonify(success_response(
            response_text="获取问答缓存统计成功",
            data=stats
        ))
        
    except Exception as e:
        print(f"[ERROR] 获取问答缓存统计失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取问答缓存统计失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_cache_list', methods=['GET'])  
def qa_cache_list():
    """获取问答缓存列表（支持分页）"""
    try:
        # 获取分页参数，默认限制50条
        limit = request.args.get('limit', 50, type=int)
        
        # 限制最大返回数量，防止一次性返回过多数据
        if limit > 500:
            limit = 500
        elif limit <= 0:
            limit = 50
        
        cache_list = redis_conversation_manager.get_qa_cache_list(limit)
        
        return jsonify(success_response(
            response_text="获取问答缓存列表成功",
            data={
                "cache_list": cache_list,
                "total_returned": len(cache_list),
                "limit_applied": limit,
                "note": "按缓存时间倒序排列，最新的在前面"
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] 获取问答缓存列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取问答缓存列表失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/qa_cache_cleanup', methods=['POST'])
def qa_cache_cleanup():
    """清空所有问答缓存"""
    try:
        if not redis_conversation_manager.is_available():
            return jsonify(internal_error_response(
                response_text="Redis连接不可用，无法执行清理操作"
            )), 500
        
        deleted_count = redis_conversation_manager.clear_all_qa_cache()
        
        return jsonify(success_response(
            response_text="问答缓存清理完成",
            data={
                "deleted_count": deleted_count,
                "cleared": deleted_count > 0,
                "cleanup_time": datetime.now().isoformat()
            }
        ))
        
    except Exception as e:
        print(f"[ERROR] 清空问答缓存失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="清空问答缓存失败，请稍后重试"
        )), 500


@app.flask_app.route('/api/v0/cache_overview_full', methods=['GET'])
def cache_overview_full():
    """获取所有缓存系统的综合概览"""
    try:
        from common.embedding_cache_manager import get_embedding_cache_manager
        from common.vanna_instance import get_vanna_instance
        
        # 获取现有的缓存统计
        vanna_cache = get_vanna_instance()
        # 直接使用应用中的缓存实例
        cache = app.cache
        
        cache_overview = {
            "conversation_aware_cache": {
                "enabled": True,
                "total_items": len(cache.cache) if hasattr(cache, 'cache') else 0,
                "sessions": list(cache.cache.keys()) if hasattr(cache, 'cache') else [],
                "cache_type": type(cache).__name__
            },
            "question_answer_cache": redis_conversation_manager.get_qa_cache_stats() if redis_conversation_manager.is_available() else {"available": False},
            "embedding_cache": get_embedding_cache_manager().get_cache_stats(),
            "redis_conversation_stats": redis_conversation_manager.get_stats() if redis_conversation_manager.is_available() else None
        }
        
        return jsonify(success_response(
            response_text="获取综合缓存概览成功",
            data=cache_overview
        ))
        
    except Exception as e:
        print(f"[ERROR] 获取综合缓存概览失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取缓存概览失败，请稍后重试"
        )), 500


# 前端JavaScript示例 - 如何维持会话
"""
// 前端需要维护一个会话ID
class ChatSession {
    constructor() {
        // 从localStorage获取或创建新的会话ID
        this.sessionId = localStorage.getItem('chat_session_id') || this.generateSessionId();
        localStorage.setItem('chat_session_id', this.sessionId);
    }
    
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    async askQuestion(question) {
        const response = await fetch('/api/v0/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                session_id: this.sessionId  // 关键：传递会话ID
            })
        });
        return await response.json();
    }
    
    // 开始新会话
    startNewSession() {
        this.sessionId = this.generateSessionId();
        localStorage.setItem('chat_session_id', this.sessionId);
    }
}

// 使用示例
const chatSession = new ChatSession();
chatSession.askQuestion("各年龄段客户的流失率如何？");
"""

print("正在启动Flask应用: http://localhost:8084")
app.run(host="0.0.0.0", port=8084, debug=True)