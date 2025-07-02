# 给dataops 对话助手返回结果
# 初始化日志系统 - 必须在最前面
from core.logging import initialize_logging, get_app_logger, set_log_context, clear_log_context
initialize_logging()

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
import sqlparse  # 用于SQL语法检查
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

# 创建app logger
logger = get_app_logger("CituApp")

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
                        logger.info(f"成功生成摘要: {summary}")
                    except Exception as e:
                        logger.warning(f"生成摘要失败: {str(e)}")
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
        logger.error(f"ask_full执行失败: {str(e)}")
        
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
        logger.error(f"citu_run_sql执行失败: {str(e)}")
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
        logger.debug(f"输入问题: '{question}'")
        conversation_id = app.cache.generate_id(question=question)
        logger.debug(f"生成的conversation_id: {conversation_id}")
        
        # 再次用相同问题测试
        conversation_id2 = app.cache.generate_id(question=question)
        logger.debug(f"再次生成的conversation_id: {conversation_id2}")
        logger.debug(f"两次ID是否相同: {conversation_id == conversation_id2}")
        
        # 检查缓存
        cached_sql = app.cache.get(id=conversation_id, field="sql")
        
        if cached_sql is not None:
            # 缓存命中
            logger.info(f"[CACHE HIT] 使用缓存结果: {conversation_id}")
            sql = cached_sql
            df = app.cache.get(id=conversation_id, field="df")
            summary = app.cache.get(id=conversation_id, field="summary")
        else:
            # 缓存未命中，执行新查询
            logger.info(f"[CACHE MISS] 执行新查询: {conversation_id}")
            
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
                    logger.info(f"成功生成摘要: {summary}")
                except Exception as e:
                    logger.warning(f"生成摘要失败: {str(e)}")
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
        logger.error(f"ask_cached执行失败: {str(e)}")
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
            logger.info(f"训练成功，训练ID为：{training_id}，问题：{question}，SQL：{sql}")
        else:
            training_id = vn.train(sql=sql)
            logger.info(f"训练成功，训练ID为：{training_id}，SQL：{sql}")

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
            logger.info("开始创建LangGraph Agent实例...")
            citu_langraph_agent = CituLangGraphAgent()
            logger.info("LangGraph Agent实例创建成功")
        except ImportError as e:
            logger.critical(f"Agent模块导入失败: {str(e)}")
            logger.critical("请检查agent模块是否存在以及依赖是否正确安装")
            raise Exception(f"Agent模块导入失败: {str(e)}")
        except Exception as e:
            logger.critical(f"LangGraph Agent实例创建失败: {str(e)}")
            logger.critical(f"错误类型: {type(e).__name__}")
            # 提供更有用的错误信息
            if "config" in str(e).lower():
                logger.critical("可能是配置文件问题，请检查配置")
            elif "llm" in str(e).lower():
                logger.critical("可能是LLM连接问题，请检查LLM配置")
            elif "tool" in str(e).lower():
                logger.critical("可能是工具加载问题，请检查工具模块")
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
                            logger.info(f"[AGENT_API] 检测到上下文类型: {context_type}")
                            break
            except Exception as e:
                logger.warning(f"获取上下文类型失败: {str(e)}")
        
        # 4. 检查缓存（新逻辑：放宽使用条件，严控存储条件）
        cached_answer = redis_conversation_manager.get_cached_answer(question, context)
        if cached_answer:
            logger.info(f"[AGENT_API] 使用缓存答案")
            
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
                records=cached_answer.get("query_result"),  # 修改：query_result改为records
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
            logger.info(f"[AGENT_API] 使用上下文，长度: {len(context)}字符")
        else:
            enhanced_question = question
            logger.info(f"[AGENT_API] 新对话，无上下文")
        
        # 7. 确定最终使用的路由模式（优先级逻辑）
        if api_routing_mode:
            # API传了参数，优先使用
            effective_routing_mode = api_routing_mode
            logger.info(f"[AGENT_API] 使用API指定的路由模式: {effective_routing_mode}")
        else:
            # API没传参数，使用配置文件
            try:
                from app_config import QUESTION_ROUTING_MODE
                effective_routing_mode = QUESTION_ROUTING_MODE
                logger.info(f"[AGENT_API] 使用配置文件路由模式: {effective_routing_mode}")
            except ImportError:
                effective_routing_mode = "hybrid"
                logger.info(f"[AGENT_API] 配置文件读取失败，使用默认路由模式: {effective_routing_mode}")
        
        # 8. 现有Agent处理逻辑（修改为传递路由模式）
        try:
            agent = get_citu_langraph_agent()
        except Exception as e:
            logger.critical(f"Agent初始化失败: {str(e)}")
            return jsonify(service_unavailable_response(
                response_text="AI服务暂时不可用，请稍后重试",
                can_retry=True
            )), 503
        
        # 异步调用Agent处理问题
        import asyncio
        agent_result = asyncio.run(agent.process_question(
            question=enhanced_question,  # 使用增强后的问题
            session_id=browser_session_id,
            context_type=context_type,  # 传递上下文类型
            routing_mode=effective_routing_mode  # 新增：传递路由模式
        ))
        
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
                records=query_result,  # 修改：query_result改为records
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
        logger.error(f"ask_agent执行失败: {str(e)}")
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
            # 修正：Agent现在是动态创建workflow的，不再有预创建的workflow属性
            health_data["workflow_compiled"] = True  # 动态创建，始终可用
            health_data["tools_count"] = len(agent.tools) if hasattr(agent, 'tools') else 0
        except Exception as e:
            health_data["message"] = f"Agent创建失败: {str(e)}"
            health_data["status"] = "unhealthy"  # 设置状态
            from common.result import health_error_response
            return jsonify(health_error_response(**health_data)), 503
        
        # 检查2: 工具导入
        try:
            from agent.tools import TOOLS
            health_data["checks"]["tools_import"] = len(TOOLS) > 0
        except Exception as e:
            health_data["message"] = f"工具导入失败: {str(e)}"
        
        # 检查3: LLM连接（简单测试）
        try:
            from agent.tools.utils import get_compatible_llm
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
                import asyncio
                # 异步调用健康检查
                test_result = asyncio.run(agent.health_check())
                health_data["test_result"] = test_result.get("status") == "healthy"
                health_data["status"] = test_result.get("status", "unknown")
                health_data["message"] = test_result.get("message", "健康检查完成")
            else:
                health_data["status"] = "degraded"
                health_data["message"] = "部分组件异常"
        except Exception as e:
            logger.error(f"健康检查异常: {str(e)}")
            import traceback
            logger.error(f"详细健康检查错误: {traceback.format_exc()}")
            health_data["status"] = "degraded"
            health_data["message"] = f"完整测试失败: {str(e)}"
        
        # 根据状态返回相应的HTTP代码 - 使用标准化健康检查响应
        from common.result import health_success_response, health_error_response
        
        if health_data["status"] == "healthy":
            return jsonify(health_success_response(**health_data))
        elif health_data["status"] == "degraded":
            return jsonify(health_error_response(**health_data)), 503
        else:
            # 确保状态设置为unhealthy
            health_data["status"] = "unhealthy"
            return jsonify(health_error_response(**health_data)), 503
            
    except Exception as e:
        logger.error(f"顶层健康检查异常: {str(e)}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")
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
        
        logger.debug(f"接收到错误SQL训练请求: question={question}, sql={sql}")
        
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
        
        logger.info(f"成功存储错误SQL，ID: {id}")
        
        from common.result import success_response
        return jsonify(success_response(
            response_text="错误SQL对已成功存储",
            data={
                "id": id,
                "message": "错误SQL对已成功存储到error_sql集合"
            }
        ))
        
    except Exception as e:
        logger.error(f"存储错误SQL失败: {str(e)}")
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

        # 为每个对话动态获取标题（第一条用户消息）
        for conversation in conversations:
            conversation_id = conversation['conversation_id']
            
            try:
                # 获取所有消息，然后取第一条用户消息作为标题
                messages = redis_conversation_manager.get_conversation_messages(conversation_id)
                
                if messages and len(messages) > 0:
                    # 找到第一条用户消息（按时间顺序）
                    first_user_message = None
                    for message in messages:
                        if message.get('role') == 'user':
                            first_user_message = message
                            break
                    
                    if first_user_message:
                        title = first_user_message.get('content', '对话').strip()
                        # 限制标题长度，保持整洁
                        if len(title) > 50:
                            conversation['conversation_title'] = title[:47] + "..."
                        else:
                            conversation['conversation_title'] = title
                    else:
                        conversation['conversation_title'] = "对话"
                else:
                    conversation['conversation_title'] = "空对话"
                    
            except Exception as e:
                logger.warning(f"获取对话标题失败 {conversation_id}: {str(e)}")
                conversation['conversation_title'] = "对话"
        
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
        context = redis_conversation_manager.get_context_for_display(conversation_id, count)
        
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
        logger.error(f"获取用户完整对话数据失败: {str(e)}")
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
        logger.error(f"获取embedding缓存统计失败: {str(e)}")
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
        logger.error(f"清空embedding缓存失败: {str(e)}")
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
                    logger.info("未找到可用的vanna实例，将创建新的数据库连接")
            except Exception as e:
                logger.info(f"获取vanna实例失败: {e}，将创建新的数据库连接")
                vanna_instance = None
            
            qa_feedback_manager = QAFeedbackManager(vanna_instance=vanna_instance)
            logger.info("QA反馈管理器实例创建成功")
        except Exception as e:
            logger.critical(f"QA反馈管理器创建失败: {str(e)}")
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
        logger.error(f"qa_feedback_query执行失败: {str(e)}")
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
        logger.error(f"qa_feedback_delete执行失败: {str(e)}")
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
        logger.error(f"qa_feedback_update执行失败: {str(e)}")
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
                    logger.info(f"正向训练成功 - ID: {record['id']}, TrainingID: {training_id}")
                else:
                    # 负向反馈 - 加入错误SQL训练集
                    training_id = vn.train_error_sql(
                        question=record['question'], 
                        sql=record['sql']
                    )
                    negative_count += 1
                    logger.info(f"负向训练成功 - ID: {record['id']}, TrainingID: {training_id}")
                
                successfully_trained_ids.append(record['id'])
                
            except Exception as e:
                logger.error(f"训练失败 - 反馈ID: {record['id']}, 错误: {e}")
                error_count += 1
        
        # 更新训练状态
        if successfully_trained_ids:
            updated_count = manager.mark_training_status(successfully_trained_ids, True)
            logger.info(f"批量更新训练状态完成，影响 {updated_count} 条记录")
        
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
        logger.error(f"qa_feedback_add_to_training执行失败: {str(e)}")
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
                "feedback_id": feedback_id
            }
        ))
        
    except Exception as e:
        logger.error(f"qa_feedback_add执行失败: {str(e)}")
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
        logger.error(f"qa_feedback_stats执行失败: {str(e)}")
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
        logger.error(f"获取问答缓存统计失败: {str(e)}")
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
        logger.error(f"获取问答缓存列表失败: {str(e)}")
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
        logger.error(f"清空问答缓存失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="清空问答缓存失败，请稍后重试"
        )), 500


# ==================== 训练数据管理接口 ====================

def validate_sql_syntax(sql: str) -> tuple[bool, str]:
    """SQL语法检查（仅对sql类型）"""
    try:
        parsed = sqlparse.parse(sql.strip())
        
        if not parsed or not parsed[0].tokens:
            return False, "SQL语法错误：空语句"
        
        # 基本语法检查
        sql_upper = sql.strip().upper()
        if not any(sql_upper.startswith(keyword) for keyword in 
                  ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']):
            return False, "SQL语法错误：不是有效的SQL语句"
        
        # 安全检查：禁止危险的SQL操作
        dangerous_operations = ['UPDATE', 'DELETE', 'ALERT', 'DROP']
        for operation in dangerous_operations:
            if sql_upper.startswith(operation):
                return False, f'在训练集中禁止使用"{",".join(dangerous_operations)}"'
        
        return True, ""
    except Exception as e:
        return False, f"SQL语法错误：{str(e)}"

def paginate_data(data_list: list, page: int, page_size: int):
    """分页处理算法"""
    total = len(data_list)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_data = data_list[start_idx:end_idx]
    
    return {
        "data": page_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": end_idx < total,
            "has_prev": page > 1
        }
    }

def filter_by_type(data_list: list, training_data_type: str):
    """按类型筛选算法"""
    if not training_data_type:
        return data_list
    
    return [
        record for record in data_list 
        if record.get('training_data_type') == training_data_type
    ]

def search_in_data(data_list: list, search_keyword: str):
    """在数据中搜索关键词"""
    if not search_keyword:
        return data_list
    
    keyword_lower = search_keyword.lower()
    return [
        record for record in data_list
        if (record.get('question') and keyword_lower in record['question'].lower()) or
           (record.get('content') and keyword_lower in record['content'].lower())
    ]

def process_single_training_item(item: dict, index: int) -> dict:
    """处理单个训练数据项"""
    training_type = item.get('training_data_type')
    
    if training_type == 'sql':
        sql = item.get('sql')
        if not sql:
            raise ValueError("SQL字段是必需的")
        
        # SQL语法检查
        is_valid, error_msg = validate_sql_syntax(sql)
        if not is_valid:
            raise ValueError(error_msg)
        
        question = item.get('question')
        if question:
            training_id = vn.train(question=question, sql=sql)
        else:
            training_id = vn.train(sql=sql)
            
    elif training_type == 'error_sql':
        # error_sql不需要语法检查
        question = item.get('question')
        sql = item.get('sql')
        if not question or not sql:
            raise ValueError("question和sql字段都是必需的")
        training_id = vn.train_error_sql(question=question, sql=sql)
        
    elif training_type == 'documentation':
        content = item.get('content')
        if not content:
            raise ValueError("content字段是必需的")
        training_id = vn.train(documentation=content)
        
    elif training_type == 'ddl':
        ddl = item.get('ddl')
        if not ddl:
            raise ValueError("ddl字段是必需的")
        training_id = vn.train(ddl=ddl)
        
    else:
        raise ValueError(f"不支持的训练数据类型: {training_type}")
    
    return {
        "index": index,
        "success": True,
        "training_id": training_id,
        "type": training_type,
        "message": f"{training_type}训练数据创建成功"
    }

def get_total_training_count():
    """获取当前训练数据总数"""
    try:
        training_data = vn.get_training_data()
        if training_data is not None and not training_data.empty:
            return len(training_data)
        return 0
    except Exception as e:
        logger.warning(f"获取训练数据总数失败: {e}")
        return 0

@app.flask_app.route('/api/v0/training_data/query', methods=['POST'])
def training_data_query():
    """
    分页查询训练数据API
    支持类型筛选、搜索和排序功能
    """
    try:
        req = request.get_json(force=True)
        
        # 解析参数，设置默认值
        page = req.get('page', 1)
        page_size = req.get('page_size', 20)
        training_data_type = req.get('training_data_type')
        sort_by = req.get('sort_by', 'id')
        sort_order = req.get('sort_order', 'desc')
        search_keyword = req.get('search_keyword')
        
        # 参数验证
        if page < 1:
            return jsonify(bad_request_response(
                response_text="页码必须大于0",
                missing_params=["page"]
            )), 400
        
        if page_size < 1 or page_size > 100:
            return jsonify(bad_request_response(
                response_text="每页大小必须在1-100之间",
                missing_params=["page_size"]
            )), 400
        
        if search_keyword and len(search_keyword) > 100:
            return jsonify(bad_request_response(
                response_text="搜索关键词最大长度为100字符",
                missing_params=["search_keyword"]
            )), 400
        
        # 获取训练数据
        training_data = vn.get_training_data()
        
        if training_data is None or training_data.empty:
            return jsonify(success_response(
                response_text="查询成功，暂无训练数据",
                data={
                    "records": [],
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    },
                    "filters_applied": {
                        "training_data_type": training_data_type,
                        "search_keyword": search_keyword
                    }
                }
            ))
        
        # 转换为列表格式
        records = training_data.to_dict(orient="records")
        
        # 应用筛选条件
        if training_data_type:
            records = filter_by_type(records, training_data_type)
        
        if search_keyword:
            records = search_in_data(records, search_keyword)
        
        # 排序
        if sort_by in ['id', 'training_data_type']:
            reverse = (sort_order.lower() == 'desc')
            records.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse)
        
        # 分页
        paginated_result = paginate_data(records, page, page_size)
        
        return jsonify(success_response(
            response_text=f"查询成功，共找到 {paginated_result['pagination']['total']} 条记录",
            data={
                "records": paginated_result["data"],
                "pagination": paginated_result["pagination"],
                "filters_applied": {
                    "training_data_type": training_data_type,
                    "search_keyword": search_keyword
                }
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_query执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询训练数据失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/training_data/create', methods=['POST'])
def training_data_create():
    """
    创建训练数据API
    支持单条和批量创建，支持四种数据类型
    """
    try:
        req = request.get_json(force=True)
        data = req.get('data')
        
        if not data:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：data",
                missing_params=["data"]
            )), 400
        
        # 统一处理为列表格式
        if isinstance(data, dict):
            data_list = [data]
        elif isinstance(data, list):
            data_list = data
        else:
            return jsonify(bad_request_response(
                response_text="data字段格式错误，应为对象或数组"
            )), 400
        
        # 批量操作限制
        if len(data_list) > 50:
            return jsonify(bad_request_response(
                response_text="批量操作最大支持50条记录"
            )), 400
        
        results = []
        successful_count = 0
        type_summary = {"sql": 0, "documentation": 0, "ddl": 0, "error_sql": 0}
        
        for index, item in enumerate(data_list):
            try:
                result = process_single_training_item(item, index)
                results.append(result)
                if result['success']:
                    successful_count += 1
                    type_summary[result['type']] += 1
            except Exception as e:
                results.append({
                    "index": index,
                    "success": False,
                    "type": item.get('training_data_type', 'unknown'),
                    "error": str(e),
                    "message": "创建失败"
                })
        
        # 获取创建后的总记录数
        current_total = get_total_training_count()
        
        return jsonify(success_response(
            response_text="训练数据创建完成",
            data={
                "total_requested": len(data_list),
                "successfully_created": successful_count,
                "failed_count": len(data_list) - successful_count,
                "results": results,
                "summary": type_summary,
                "current_total_count": current_total
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_create执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建训练数据失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/training_data/delete', methods=['POST'])
def training_data_delete():
    """
    删除训练数据API
    支持批量删除
    """
    try:
        req = request.get_json(force=True)
        ids = req.get('ids', [])
        confirm = req.get('confirm', False)
        
        if not ids or not isinstance(ids, list):
            return jsonify(bad_request_response(
                response_text="缺少有效的ID列表",
                missing_params=["ids"]
            )), 400
        
        if not confirm:
            return jsonify(bad_request_response(
                response_text="删除操作需要确认，请设置confirm为true"
            )), 400
        
        # 批量操作限制
        if len(ids) > 50:
            return jsonify(bad_request_response(
                response_text="批量删除最大支持50条记录"
            )), 400
        
        deleted_ids = []
        failed_ids = []
        failed_details = []
        
        for training_id in ids:
            try:
                success = vn.remove_training_data(training_id)
                if success:
                    deleted_ids.append(training_id)
                else:
                    failed_ids.append(training_id)
                    failed_details.append({
                        "id": training_id,
                        "error": "记录不存在或删除失败"
                    })
            except Exception as e:
                failed_ids.append(training_id)
                failed_details.append({
                    "id": training_id,
                    "error": str(e)
                })
        
        # 获取删除后的总记录数
        current_total = get_total_training_count()
        
        return jsonify(success_response(
            response_text="训练数据删除完成",
            data={
                "total_requested": len(ids),
                "successfully_deleted": len(deleted_ids),
                "failed_count": len(failed_ids),
                "deleted_ids": deleted_ids,
                "failed_ids": failed_ids,
                "failed_details": failed_details,
                "current_total_count": current_total
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_delete执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除训练数据失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/training_data/stats', methods=['GET'])
def training_data_stats():
    """
    获取训练数据统计信息API
    """
    try:
        training_data = vn.get_training_data()
        
        if training_data is None or training_data.empty:
            return jsonify(success_response(
                response_text="统计信息获取成功",
                data={
                    "total_count": 0,
                    "type_breakdown": {
                        "sql": 0,
                        "documentation": 0,
                        "ddl": 0,
                        "error_sql": 0
                    },
                    "type_percentages": {
                        "sql": 0.0,
                        "documentation": 0.0,
                        "ddl": 0.0,
                        "error_sql": 0.0
                    },
                    "last_updated": datetime.now().isoformat()
                }
            ))
        
        total_count = len(training_data)
        
        # 统计各类型数量
        type_breakdown = {"sql": 0, "documentation": 0, "ddl": 0, "error_sql": 0}
        
        if 'training_data_type' in training_data.columns:
            type_counts = training_data['training_data_type'].value_counts()
            for data_type, count in type_counts.items():
                if data_type in type_breakdown:
                    type_breakdown[data_type] = int(count)
        
        # 计算百分比
        type_percentages = {}
        for data_type, count in type_breakdown.items():
            type_percentages[data_type] = round(count / max(total_count, 1) * 100, 2)
        
        return jsonify(success_response(
            response_text="统计信息获取成功",
            data={
                "total_count": total_count,
                "type_breakdown": type_breakdown,
                "type_percentages": type_percentages,
                "last_updated": datetime.now().isoformat()
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_stats执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取统计信息失败，请稍后重试"
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
        logger.error(f"获取综合缓存概览失败: {str(e)}")
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

# ==================== Data Pipeline API ====================

# 导入简化的Data Pipeline模块
import asyncio
import os
from threading import Thread
from flask import send_file

from data_pipeline.api.simple_workflow import SimpleWorkflowManager
from data_pipeline.api.simple_file_manager import SimpleFileManager

# 创建简化的管理器
data_pipeline_manager = None
data_pipeline_file_manager = None

def get_data_pipeline_manager():
    """获取Data Pipeline管理器单例"""
    global data_pipeline_manager
    if data_pipeline_manager is None:
        data_pipeline_manager = SimpleWorkflowManager()
    return data_pipeline_manager

def get_data_pipeline_file_manager():
    """获取Data Pipeline文件管理器单例"""
    global data_pipeline_file_manager
    if data_pipeline_file_manager is None:
        data_pipeline_file_manager = SimpleFileManager()
    return data_pipeline_file_manager

# ==================== 简化的Data Pipeline API端点 ====================

@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['POST'])
def create_data_pipeline_task():
    """创建数据管道任务"""
    try:
        req = request.get_json(force=True)
        
        # table_list_file和business_context现在都是可选参数
        # 如果未提供table_list_file，将使用文件上传模式
        
        # 创建任务（支持可选的db_connection参数）
        manager = get_data_pipeline_manager()
        task_id = manager.create_task(
            table_list_file=req.get('table_list_file'),
            business_context=req.get('business_context'),
            db_name=req.get('db_name'),  # 可选参数，用于指定特定数据库名称
            db_connection=req.get('db_connection'),  # 可选参数，用于指定数据库连接字符串
            task_name=req.get('task_name'),  # 可选参数，用于指定任务名称
            enable_sql_validation=req.get('enable_sql_validation', True),
            enable_llm_repair=req.get('enable_llm_repair', True),
            modify_original_file=req.get('modify_original_file', True),
            enable_training_data_load=req.get('enable_training_data_load', True)
        )
        
        # 获取任务信息
        task_info = manager.get_task_status(task_id)
        
        response_data = {
            "task_id": task_id,
            "task_name": task_info.get('task_name'),
            "status": task_info.get('status'),
            "created_at": task_info.get('created_at').isoformat() if task_info.get('created_at') else None
        }
        
        # 检查是否为文件上传模式
        file_upload_mode = not req.get('table_list_file')
        response_message = "任务创建成功"
        
        if file_upload_mode:
            response_data["file_upload_mode"] = True
            response_data["next_step"] = f"POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list"
            response_message += "，请上传表清单文件后再执行任务"
        
        return jsonify(success_response(
            response_text=response_message,
            data=response_data
        )), 201
        
    except Exception as e:
        logger.error(f"创建数据管道任务失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建任务失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/execute', methods=['POST'])
def execute_data_pipeline_task(task_id):
    """执行数据管道任务"""
    try:
        req = request.get_json(force=True) if request.is_json else {}
        execution_mode = req.get('execution_mode', 'complete')
        step_name = req.get('step_name')
        
        # 验证执行模式
        if execution_mode not in ['complete', 'step']:
            return jsonify(bad_request_response(
                response_text="无效的执行模式，必须是 'complete' 或 'step'",
                invalid_params=['execution_mode']
            )), 400
        
        # 如果是步骤执行模式，验证步骤名称
        if execution_mode == 'step':
            if not step_name:
                return jsonify(bad_request_response(
                    response_text="步骤执行模式需要指定step_name",
                    missing_params=['step_name']
                )), 400
            
            valid_steps = ['ddl_generation', 'qa_generation', 'sql_validation', 'training_load']
            if step_name not in valid_steps:
                return jsonify(bad_request_response(
                    response_text=f"无效的步骤名称，支持的步骤: {', '.join(valid_steps)}",
                    invalid_params=['step_name']
                )), 400
        
        # 检查任务是否存在
        manager = get_data_pipeline_manager()
        task_info = manager.get_task_status(task_id)
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 使用subprocess启动独立进程执行任务
        def run_task_subprocess():
            try:
                import subprocess
                import sys
                from pathlib import Path
                
                # 构建执行命令
                python_executable = sys.executable
                script_path = Path(__file__).parent / "data_pipeline" / "task_executor.py"
                
                cmd = [
                    python_executable,
                    str(script_path),
                    "--task-id", task_id,
                    "--execution-mode", execution_mode
                ]
                
                if step_name:
                    cmd.extend(["--step-name", step_name])
                
                logger.info(f"启动任务进程: {' '.join(cmd)}")
                
                # 启动后台进程（不等待完成）
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=Path(__file__).parent
                )
                
                logger.info(f"任务进程已启动: PID={process.pid}, task_id={task_id}")
                
            except Exception as e:
                logger.error(f"启动任务进程失败: {task_id}, 错误: {str(e)}")
        
        # 在新线程中启动subprocess（避免阻塞API响应）
        thread = Thread(target=run_task_subprocess, daemon=True)
        thread.start()
        
        response_data = {
            "task_id": task_id,
            "execution_mode": execution_mode,
            "step_name": step_name if execution_mode == 'step' else None,
            "message": "任务正在后台执行，请通过状态接口查询进度"
        }
        
        return jsonify(success_response(
            response_text="任务执行已启动",
            data=response_data
        )), 202
        
    except Exception as e:
        logger.error(f"启动数据管道任务执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="启动任务执行失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>', methods=['GET'])
def get_data_pipeline_task_status(task_id):
    """
    获取数据管道任务状态
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取任务状态成功",
        "data": {
            "task_id": "task_20250627_143052",
            "status": "in_progress",
            "step_status": {
                "ddl_generation": "completed",
                "qa_generation": "running",
                "sql_validation": "pending",
                "training_load": "pending"
            },
            "created_at": "2025-06-27T14:30:52",
            "started_at": "2025-06-27T14:31:00",
            "parameters": {...},
            "current_execution": {...},
            "total_executions": 2
        }
    }
    """
    try:
        manager = get_data_pipeline_manager()
        task_info = manager.get_task_status(task_id)
        
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 获取步骤状态
        steps = manager.get_task_steps(task_id)
        current_step = None
        for step in steps:
            if step['step_status'] == 'running':
                current_step = step
                break
        
        # 构建步骤状态摘要
        step_status_summary = {}
        for step in steps:
            step_status_summary[step['step_name']] = step['step_status']
        
        response_data = {
            "task_id": task_info['task_id'],
            "task_name": task_info.get('task_name'),
            "status": task_info['status'],
            "step_status": step_status_summary,
            "created_at": task_info['created_at'].isoformat() if task_info.get('created_at') else None,
            "started_at": task_info['started_at'].isoformat() if task_info.get('started_at') else None,
            "completed_at": task_info['completed_at'].isoformat() if task_info.get('completed_at') else None,
            "parameters": task_info.get('parameters', {}),
            "result": task_info.get('result'),
            "error_message": task_info.get('error_message'),
            "current_step": {
                "execution_id": current_step['execution_id'],
                "step": current_step['step_name'],
                "status": current_step['step_status'],
                "started_at": current_step['started_at'].isoformat() if current_step and current_step.get('started_at') else None
            } if current_step else None,
            "total_steps": len(steps),
            "steps": [{
                "step_name": step['step_name'],
                "step_status": step['step_status'],
                "started_at": step['started_at'].isoformat() if step.get('started_at') else None,
                "completed_at": step['completed_at'].isoformat() if step.get('completed_at') else None,
                "error_message": step.get('error_message')
            } for step in steps]
        }
        
        return jsonify(success_response(
            response_text="获取任务状态成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"获取数据管道任务状态失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取任务状态失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/logs', methods=['GET'])
def get_data_pipeline_task_logs(task_id):
    """
    获取数据管道任务日志（从任务目录文件读取）
    
    查询参数:
    - limit: 日志行数限制，默认100
    - level: 日志级别过滤，可选
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取任务日志成功",
        "data": {
            "task_id": "task_20250627_143052",
            "logs": [
                {
                    "timestamp": "2025-06-27 14:30:52",
                    "level": "INFO",
                    "message": "任务开始执行"
                }
            ],
            "total": 15,
            "source": "file"
        }
    }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        level = request.args.get('level')
        
        # 限制最大查询数量
        limit = min(limit, 1000)
        
        manager = get_data_pipeline_manager()
        
        # 验证任务是否存在
        task_info = manager.get_task_status(task_id)
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 获取任务目录下的日志文件
        import os
        from pathlib import Path
        
        # 获取项目根目录的绝对路径
        project_root = Path(__file__).parent.absolute()
        task_dir = project_root / "data_pipeline" / "training_data" / task_id
        log_file = task_dir / "data_pipeline.log"
        
        logs = []
        if log_file.exists():
            try:
                # 读取日志文件的最后N行
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                # 取最后limit行
                recent_lines = lines[-limit:] if len(lines) > limit else lines
                
                # 解析日志行
                import re
                log_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.+?): (.+)$'
                
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    match = re.match(log_pattern, line)
                    if match:
                        timestamp, log_level, logger_name, message = match.groups()
                        
                        # 级别过滤
                        if level and log_level != level.upper():
                            continue
                            
                        logs.append({
                            "timestamp": timestamp,
                            "level": log_level,
                            "logger": logger_name,
                            "message": message
                        })
                    else:
                        # 处理多行日志（如异常堆栈）
                        if logs:
                            logs[-1]["message"] += f"\n{line}"
                        
            except Exception as e:
                logger.error(f"读取日志文件失败: {e}")
        
        response_data = {
            "task_id": task_id,
            "logs": logs,
            "total": len(logs),
            "source": "file",
            "log_file": str(log_file) if log_file.exists() else None
        }
        
        return jsonify(success_response(
            response_text="获取任务日志成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"获取数据管道任务日志失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取任务日志失败，请稍后重试"
        )), 500


@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['GET'])
def list_data_pipeline_tasks():
    """获取数据管道任务列表"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        status_filter = request.args.get('status')
        
        # 限制查询数量
        limit = min(limit, 100)
        
        manager = get_data_pipeline_manager()
        tasks = manager.get_tasks_list(
            limit=limit,
            offset=offset,
            status_filter=status_filter
        )
        
        # 格式化任务列表
        formatted_tasks = []
        for task in tasks:
            formatted_tasks.append({
                "task_id": task.get('task_id'),
                "task_name": task.get('task_name'),
                "status": task.get('status'),
                "step_status": task.get('step_status'),
                "created_at": task['created_at'].isoformat() if task.get('created_at') else None,
                "started_at": task['started_at'].isoformat() if task.get('started_at') else None,
                "completed_at": task['completed_at'].isoformat() if task.get('completed_at') else None,
                "created_by": task.get('by_user'),
                "db_name": task.get('db_name'),
                "business_context": task.get('parameters', {}).get('business_context') if task.get('parameters') else None,
                # 新增字段
                "directory_exists": task.get('directory_exists', True),  # 默认为True，兼容旧数据
                "updated_at": task['updated_at'].isoformat() if task.get('updated_at') else None
            })
        
        response_data = {
            "tasks": formatted_tasks,
            "total": len(formatted_tasks),
            "limit": limit,
            "offset": offset
        }
        
        return jsonify(success_response(
            response_text="获取任务列表成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"获取数据管道任务列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取任务列表失败，请稍后重试"
        )), 500

# ==================== 表检查API端点 ====================

import asyncio
from data_pipeline.api.table_inspector_api import TableInspectorAPI

@app.flask_app.route('/api/v0/database/tables', methods=['POST'])
def get_database_tables():
    """
    获取数据库表列表
    
    请求体:
    {
        "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",  // 可选，不传则使用默认配置
        "schema": "public,ods"  // 可选，支持多个schema用逗号分隔，默认为public
    }
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取表列表成功",
        "data": {
            "tables": ["public.table1", "public.table2", "ods.table3"],
            "total": 3,
            "schemas": ["public", "ods"]
        }
    }
    """
    try:
        req = request.get_json(force=True)
        
        # 处理数据库连接参数（可选）
        db_connection = req.get('db_connection')
        if not db_connection:
            # 使用app_config的默认数据库配置
            import app_config
            db_params = app_config.APP_DB_CONFIG
            db_connection = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}:{db_params['port']}/{db_params['dbname']}"
            logger.info("使用默认数据库配置获取表列表")
        else:
            logger.info("使用用户指定的数据库配置获取表列表")
        
        # 可选参数
        schema = req.get('schema', '')
        
        # 创建表检查API实例
        table_inspector = TableInspectorAPI()
        
        # 使用asyncio运行异步方法
        async def get_tables():
            return await table_inspector.get_tables_list(db_connection, schema)
        
        # 在新的事件循环中运行异步方法
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tables = loop.run_until_complete(get_tables())
        finally:
            loop.close()
        
        # 解析schema信息
        parsed_schemas = table_inspector._parse_schemas(schema)
        
        response_data = {
            "tables": tables,
            "total": len(tables),
            "schemas": parsed_schemas,
            "db_connection_info": {
                "database": db_connection.split('/')[-1].split('?')[0] if '/' in db_connection else "unknown"
            }
        }
        
        return jsonify(success_response(
            response_text="获取表列表成功",
            data=response_data
        )), 200
        
    except Exception as e:
        logger.error(f"获取数据库表列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text=f"获取表列表失败: {str(e)}"
        )), 500

@app.flask_app.route('/api/v0/database/table/ddl', methods=['POST'])
def get_table_ddl():
    """
    获取表的DDL语句或MD文档
    
    请求体:
    {
        "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",  // 可选，不传则使用默认配置
        "table": "public.test",
        "business_context": "这是高速公路服务区的相关数据",  // 可选
        "type": "ddl"  // 可选，支持ddl/md/both，默认为ddl
    }
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取表DDL成功",
        "data": {
            "ddl": "create table public.test (...);",
            "md": "## test表...",  // 仅当type为md或both时返回
            "table_info": {
                "table_name": "test",
                "schema_name": "public",
                "full_name": "public.test",
                "comment": "测试表",
                "field_count": 10,
                "row_count": 1000
            },
            "fields": [...]
        }
    }
    """
    try:
        req = request.get_json(force=True)
        
        # 处理参数（table仍为必需，db_connection可选）
        table = req.get('table')
        db_connection = req.get('db_connection')
        
        if not table:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：table",
                missing_params=['table']
            )), 400
        
        if not db_connection:
            # 使用app_config的默认数据库配置
            import app_config
            db_params = app_config.APP_DB_CONFIG
            db_connection = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}:{db_params['port']}/{db_params['dbname']}"
            logger.info("使用默认数据库配置获取表DDL")
        else:
            logger.info("使用用户指定的数据库配置获取表DDL")
        
        # 可选参数
        business_context = req.get('business_context', '')
        output_type = req.get('type', 'ddl')
        
        # 验证type参数
        valid_types = ['ddl', 'md', 'both']
        if output_type not in valid_types:
            return jsonify(bad_request_response(
                response_text=f"无效的type参数: {output_type}，支持的值: {valid_types}",
                invalid_params=['type']
            )), 400
        
        # 创建表检查API实例
        table_inspector = TableInspectorAPI()
        
        # 使用asyncio运行异步方法
        async def get_ddl():
            return await table_inspector.get_table_ddl(
                db_connection=db_connection,
                table=table,
                business_context=business_context,
                output_type=output_type
            )
        
        # 在新的事件循环中运行异步方法
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(get_ddl())
        finally:
            loop.close()
        
        response_data = {
            **result,
            "generation_info": {
                "business_context": business_context,
                "output_type": output_type,
                "has_llm_comments": bool(business_context),
                "database": db_connection.split('/')[-1].split('?')[0] if '/' in db_connection else "unknown"
            }
        }
        
        return jsonify(success_response(
            response_text=f"获取表{output_type.upper()}成功",
            data=response_data
        )), 200
        
    except Exception as e:
        logger.error(f"获取表DDL失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text=f"获取表{output_type.upper() if 'output_type' in locals() else 'DDL'}失败: {str(e)}"
        )), 500

# ==================== Data Pipeline 文件管理 API ====================

from flask import send_file

# 创建文件管理器
data_pipeline_file_manager = None

def get_data_pipeline_file_manager():
    """获取Data Pipeline文件管理器单例"""
    global data_pipeline_file_manager
    if data_pipeline_file_manager is None:
        data_pipeline_file_manager = SimpleFileManager()
    return data_pipeline_file_manager

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/files', methods=['GET'])
def get_data_pipeline_task_files(task_id):
    """获取任务文件列表"""
    try:
        file_manager = get_data_pipeline_file_manager()
        
        # 获取任务文件
        files = file_manager.get_task_files(task_id)
        directory_info = file_manager.get_directory_info(task_id)
        
        # 格式化文件信息
        formatted_files = []
        for file_info in files:
            formatted_files.append({
                "file_name": file_info['file_name'],
                "file_type": file_info['file_type'],
                "file_size": file_info['file_size'],
                "file_size_formatted": file_info['file_size_formatted'],
                "created_at": file_info['created_at'].isoformat() if file_info.get('created_at') else None,
                "modified_at": file_info['modified_at'].isoformat() if file_info.get('modified_at') else None,
                "is_readable": file_info['is_readable']
            })
        
        response_data = {
            "task_id": task_id,
            "files": formatted_files,
            "directory_info": directory_info
        }
        
        return jsonify(success_response(
            response_text="获取任务文件列表成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"获取任务文件列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取任务文件列表失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/files/<file_name>', methods=['GET'])
def download_data_pipeline_task_file(task_id, file_name):
    """下载任务文件"""
    try:
        logger.info(f"开始下载文件: task_id={task_id}, file_name={file_name}")
        
        # 直接构建文件路径，避免依赖数据库
        from pathlib import Path
        import os
        
        # 获取项目根目录的绝对路径
        project_root = Path(__file__).parent.absolute()
        task_dir = project_root / "data_pipeline" / "training_data" / task_id
        file_path = task_dir / file_name
        
        logger.info(f"文件路径: {file_path}")
        
        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path}")
            return jsonify(not_found_response(
                response_text=f"文件不存在: {file_name}"
            )), 404
        
        # 检查是否为文件（而不是目录）
        if not file_path.is_file():
            logger.warning(f"路径不是文件: {file_path}")
            return jsonify(bad_request_response(
                response_text=f"路径不是有效文件: {file_name}"
            )), 400
        
        # 安全检查：确保文件在允许的目录内
        try:
            file_path.resolve().relative_to(task_dir.resolve())
        except ValueError:
            logger.warning(f"文件路径不安全: {file_path}")
            return jsonify(bad_request_response(
                response_text="非法的文件路径"
            )), 400
        
        # 检查文件是否可读
        if not os.access(file_path, os.R_OK):
            logger.warning(f"文件不可读: {file_path}")
            return jsonify(bad_request_response(
                response_text="文件不可读"
            )), 400
        
        logger.info(f"开始发送文件: {file_path}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_name
        )
        
    except Exception as e:
        logger.error(f"下载任务文件失败: task_id={task_id}, file_name={file_name}, 错误: {str(e)}", exc_info=True)
        return jsonify(internal_error_response(
            response_text="下载文件失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/upload-table-list', methods=['POST'])
def upload_table_list_file(task_id):
    """
    上传表清单文件
    
    表单参数:
    - file: 要上传的表清单文件（multipart/form-data）
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "表清单文件上传成功",
        "data": {
            "task_id": "task_20250701_123456",
            "filename": "table_list.txt",
            "file_size": 1024,
            "file_size_formatted": "1.0 KB"
        }
    }
    """
    try:
        # 验证任务是否存在
        manager = get_data_pipeline_manager()
        task_info = manager.get_task_status(task_id)
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify(bad_request_response(
                response_text="请选择要上传的表清单文件",
                missing_params=['file']
            )), 400
        
        file = request.files['file']
        
        # 验证文件名
        if file.filename == '':
            return jsonify(bad_request_response(
                response_text="请选择有效的文件"
            )), 400
        
        try:
            # 使用文件管理器上传文件
            file_manager = get_data_pipeline_file_manager()
            result = file_manager.upload_table_list_file(task_id, file)
            
            response_data = {
                "task_id": task_id,
                "filename": result["filename"],
                "file_size": result["file_size"],
                "file_size_formatted": result["file_size_formatted"],
                "upload_time": result["upload_time"].isoformat() if result.get("upload_time") else None
            }
            
            return jsonify(success_response(
                response_text="表清单文件上传成功",
                data=response_data
            )), 200
            
        except ValueError as e:
            # 文件验证错误（如文件太大、空文件等）
            return jsonify(bad_request_response(
                response_text=str(e)
            )), 400
        except Exception as e:
            logger.error(f"上传表清单文件失败: {str(e)}")
            return jsonify(internal_error_response(
                response_text="文件上传失败，请稍后重试"
            )), 500
        
    except Exception as e:
        logger.error(f"处理表清单文件上传请求失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="处理上传请求失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/table-list-info', methods=['GET'])
def get_table_list_info(task_id):
    """
    获取任务的表清单文件信息
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取表清单文件信息成功",
        "data": {
            "task_id": "task_20250701_123456",
            "has_file": true,
            "filename": "table_list.txt",
            "file_path": "./data_pipeline/training_data/task_20250701_123456/table_list.txt",
            "file_size": 1024,
            "file_size_formatted": "1.0 KB",
            "uploaded_at": "2025-07-01T12:34:56",
            "table_count": 5,
            "is_readable": true
        }
    }
    """
    try:
        file_manager = get_data_pipeline_file_manager()
        
        # 获取表清单文件信息
        table_list_info = file_manager.get_table_list_file_info(task_id)
        
        response_data = {
            "task_id": task_id,
            "has_file": table_list_info.get("exists", False),
            **table_list_info
        }
        
        return jsonify(success_response(
            response_text="获取表清单文件信息成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"获取表清单文件信息失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取表清单文件信息失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/table-list', methods=['POST'])
def create_table_list_from_names(task_id):
    """
    通过POST方式提交表名列表并创建table_list.txt文件
    
    请求体:
    {
        "tables": ["table1", "schema.table2", "table3"]
    }
    或者:
    {
        "tables": "table1,schema.table2,table3"
    }
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "表清单已成功创建",
        "data": {
            "task_id": "task_20250701_123456",
            "filename": "table_list.txt",
            "table_count": 3,
            "file_size": 45,
            "file_size_formatted": "45 B",
            "created_time": "2025-07-01T12:34:56"
        }
    }
    """
    try:
        # 验证任务是否存在
        manager = get_data_pipeline_manager()
        task_info = manager.get_task_status(task_id)
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 获取请求数据
        req = request.get_json(force=True)
        tables_param = req.get('tables')
        
        if not tables_param:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：tables",
                missing_params=['tables']
            )), 400
        
        # 处理不同格式的表名参数
        try:
            if isinstance(tables_param, str):
                # 逗号分隔的字符串格式
                table_names = [name.strip() for name in tables_param.split(',') if name.strip()]
            elif isinstance(tables_param, list):
                # 数组格式
                table_names = [str(name).strip() for name in tables_param if str(name).strip()]
            else:
                return jsonify(bad_request_response(
                    response_text="tables参数格式错误，应为字符串（逗号分隔）或数组"
                )), 400
            
            if not table_names:
                return jsonify(bad_request_response(
                    response_text="表名列表不能为空"
                )), 400
                
        except Exception as e:
            return jsonify(bad_request_response(
                response_text=f"解析tables参数失败: {str(e)}"
            )), 400
        
        try:
            # 使用文件管理器创建表清单文件
            file_manager = get_data_pipeline_file_manager()
            result = file_manager.create_table_list_from_names(task_id, table_names)
            
            response_data = {
                "task_id": task_id,
                "filename": result["filename"],
                "table_count": result["table_count"],
                "unique_table_count": result["unique_table_count"],
                "file_size": result["file_size"],
                "file_size_formatted": result["file_size_formatted"],
                "created_time": result["created_time"].isoformat() if result.get("created_time") else None,
                "original_count": len(table_names) if isinstance(table_names, list) else len(tables_param.split(','))
            }
            
            return jsonify(success_response(
                response_text=f"表清单已成功创建，包含 {result['table_count']} 个表",
                data=response_data
            )), 200
            
        except ValueError as e:
            # 表名验证错误（如格式错误、数量限制等）
            return jsonify(bad_request_response(
                response_text=str(e)
            )), 400
        except Exception as e:
            logger.error(f"创建表清单文件失败: {str(e)}")
            return jsonify(internal_error_response(
                response_text="创建表清单文件失败，请稍后重试"
            )), 500
        
    except Exception as e:
        logger.error(f"处理表清单创建请求失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="处理请求失败，请稍后重试"
        )), 500

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/files', methods=['POST'])
def upload_file_to_task(task_id):
    """
    上传文件到指定任务目录
    
    表单参数:
    - file: 要上传的文件（multipart/form-data）
    - overwrite_mode: 重名处理模式 (backup, replace, skip)，默认为backup
    
    支持的文件类型：
    - .ddl: DDL文件
    - .md: Markdown文档
    - .txt: 文本文件
    - .json: JSON文件
    - .sql: SQL文件
    - .csv: CSV文件
    
    重名处理模式：
    - backup: 备份原文件（默认）
    - replace: 直接覆盖
    - skip: 跳过上传
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "文件上传成功",
        "data": {
            "task_id": "task_20250701_123456",
            "uploaded_file": {
                "filename": "test.ddl",
                "size": 1024,
                "size_formatted": "1.0 KB",
                "uploaded_at": "2025-07-01T12:34:56",
                "overwrite_mode": "backup"
            },
            "backup_info": {  // 仅当overwrite_mode为backup且文件已存在时返回
                "had_existing_file": true,
                "backup_filename": "test.ddl_bak1",
                "backup_version": 1,
                "backup_created_at": "2025-07-01T12:34:56"
            }
        }
    }
    """
    try:
        # 验证任务是否存在
        manager = get_data_pipeline_manager()
        task_info = manager.get_task_status(task_id)
        if not task_info:
            return jsonify(not_found_response(
                response_text=f"任务不存在: {task_id}"
            )), 404
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify(bad_request_response(
                response_text="请选择要上传的文件",
                missing_params=['file']
            )), 400
        
        file = request.files['file']
        
        # 验证文件名
        if file.filename == '':
            return jsonify(bad_request_response(
                response_text="请选择有效的文件"
            )), 400
        
        # 获取重名处理模式
        overwrite_mode = request.form.get('overwrite_mode', 'backup')
        
        # 验证重名处理模式
        valid_modes = ['backup', 'replace', 'skip']
        if overwrite_mode not in valid_modes:
            return jsonify(bad_request_response(
                response_text=f"无效的overwrite_mode参数: {overwrite_mode}，支持的值: {valid_modes}",
                invalid_params=['overwrite_mode']
            )), 400
        
        try:
            # 使用文件管理器上传文件
            file_manager = get_data_pipeline_file_manager()
            result = file_manager.upload_file_to_task(task_id, file, file.filename, overwrite_mode)
            
            # 检查是否跳过上传
            if result.get('skipped'):
                return jsonify(success_response(
                    response_text=result.get('message', '文件已存在，跳过上传'),
                    data=result
                )), 200
            
            return jsonify(success_response(
                response_text="文件上传成功",
                data=result
            )), 200
            
        except ValueError as e:
            # 文件验证错误（如文件太大、空文件、不支持的类型等）
            return jsonify(bad_request_response(
                response_text=str(e)
            )), 400
        except Exception as e:
            logger.error(f"上传文件失败: {str(e)}")
            return jsonify(internal_error_response(
                response_text="文件上传失败，请稍后重试"
            )), 500
        
    except Exception as e:
        logger.error(f"处理文件上传请求失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="处理上传请求失败，请稍后重试"
        )), 500

# ==================== 任务目录删除API ====================

import shutil
from pathlib import Path
from datetime import datetime
import psycopg2
from app_config import PGVECTOR_CONFIG

def delete_task_directory_simple(task_id, delete_database_records=False):
    """
    简单的任务目录删除功能
    - 删除 data_pipeline/training_data/{task_id} 目录
    - 更新数据库中的 directory_exists 字段
    - 可选：删除数据库记录
    """
    try:
        # 1. 删除目录
        project_root = Path(__file__).parent.absolute()
        task_dir = project_root / "data_pipeline" / "training_data" / task_id
        
        deleted_files_count = 0
        deleted_size = 0
        
        if task_dir.exists():
            # 计算删除前的统计信息
            for file_path in task_dir.rglob('*'):
                if file_path.is_file():
                    deleted_files_count += 1
                    deleted_size += file_path.stat().st_size
            
            # 删除目录
            shutil.rmtree(task_dir)
            directory_deleted = True
        else:
            directory_deleted = False
        
        # 2. 更新数据库
        database_records_deleted = False
        
        try:
            conn = psycopg2.connect(**PGVECTOR_CONFIG)
            cur = conn.cursor()
            
            if delete_database_records:
                # 删除任务步骤记录
                cur.execute("DELETE FROM data_pipeline_task_steps WHERE task_id = %s", (task_id,))
                # 删除任务主记录
                cur.execute("DELETE FROM data_pipeline_tasks WHERE task_id = %s", (task_id,))
                database_records_deleted = True
            else:
                # 只更新目录状态
                cur.execute("""
                    UPDATE data_pipeline_tasks 
                    SET directory_exists = FALSE, updated_at = CURRENT_TIMESTAMP 
                    WHERE task_id = %s
                """, (task_id,))
            
            conn.commit()
            cur.close()
            conn.close()
            
        except Exception as db_error:
            logger.error(f"数据库操作失败: {db_error}")
            # 数据库失败不影响文件删除的结果
        
        # 3. 格式化文件大小
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024**2:
                return f"{size_bytes/1024:.1f} KB"
            elif size_bytes < 1024**3:
                return f"{size_bytes/(1024**2):.1f} MB"
            else:
                return f"{size_bytes/(1024**3):.1f} GB"
        
        return {
            "success": True,
            "task_id": task_id,
            "directory_deleted": directory_deleted,
            "database_records_deleted": database_records_deleted,
            "deleted_files_count": deleted_files_count,
            "deleted_size": format_size(deleted_size),
            "deleted_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"删除任务目录失败: {task_id}, 错误: {str(e)}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
            "error_code": "DELETE_FAILED"
        }

@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['DELETE'])
def delete_tasks():
    """删除任务目录（支持单个和批量）"""
    try:
        # 获取请求参数
        req = request.get_json(force=True)
        
        # 验证必需参数
        task_ids = req.get('task_ids')
        confirm = req.get('confirm')
        
        if not task_ids:
            return jsonify(bad_request_response(
                response_text="缺少必需参数: task_ids",
                missing_params=['task_ids']
            )), 400
        
        if not confirm:
            return jsonify(bad_request_response(
                response_text="缺少必需参数: confirm",
                missing_params=['confirm']
            )), 400
        
        if confirm != True:
            return jsonify(bad_request_response(
                response_text="confirm参数必须为true以确认删除操作"
            )), 400
        
        if not isinstance(task_ids, list) or len(task_ids) == 0:
            return jsonify(bad_request_response(
                response_text="task_ids必须是非空的任务ID列表"
            )), 400
        
        # 获取可选参数
        delete_database_records = req.get('delete_database_records', False)
        continue_on_error = req.get('continue_on_error', True)
        
        # 执行批量删除操作
        deleted_tasks = []
        failed_tasks = []
        total_size_freed = 0
        
        for task_id in task_ids:
            result = delete_task_directory_simple(task_id, delete_database_records)
            
            if result["success"]:
                deleted_tasks.append(result)
                # 累计释放的空间大小（这里简化处理，实际应该解析size字符串）
            else:
                failed_tasks.append({
                    "task_id": task_id,
                    "error": result["error"],
                    "error_code": result.get("error_code", "UNKNOWN")
                })
                
                if not continue_on_error:
                    break
        
        # 构建响应
        summary = {
            "total_requested": len(task_ids),
            "successfully_deleted": len(deleted_tasks),
            "failed": len(failed_tasks)
        }
        
        batch_result = {
            "deleted_tasks": deleted_tasks,
            "failed_tasks": failed_tasks,
            "summary": summary,
            "deleted_at": datetime.now().isoformat()
        }
        
        if len(task_ids) == 1:
            # 单个删除
            if summary["failed"] == 0:
                message = "任务目录删除成功"
            else:
                message = "任务目录删除失败"
        else:
            # 批量删除
            if summary["failed"] == 0:
                message = "批量删除完成"
            elif summary["successfully_deleted"] == 0:
                message = "批量删除失败"
            else:
                message = "批量删除部分完成"
        
        return jsonify(success_response(
            response_text=message,
            data=batch_result
        )), 200
        
    except Exception as e:
        logger.error(f"删除任务失败: 错误: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除任务失败，请稍后重试"
        )), 500

logger.info("启动Flask应用: http://localhost:8084")
app.run(host="0.0.0.0", port=8084, debug=True)
