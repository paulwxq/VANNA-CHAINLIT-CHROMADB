"""
统一 API 服务
集成 citu_app.py 指定API 和 react_agent/api.py 的所有功能
提供数据库问答、Redis对话管理、QA反馈、训练数据管理、React Agent等功能

使用普通 Flask 应用 + ASGI 包装实现异步支持
"""
import asyncio
import logging
import atexit
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, TYPE_CHECKING, Union
import signal

if TYPE_CHECKING:
    from react_agent.agent import CustomReactAgent

# 初始化日志系统 - 必须在最前面
from core.logging import initialize_logging, get_app_logger
initialize_logging()

# 标准 Flask 导入
from flask import Flask, request, jsonify, session
import redis.asyncio as redis

# 基础依赖
import pandas as pd
import json
import sqlparse

# 项目模块导入
from core.vanna_llm_factory import create_vanna_instance
from common.redis_conversation_manager import RedisConversationManager
from common.qa_feedback_manager import QAFeedbackManager
from common.result import (
    success_response, bad_request_response, not_found_response, internal_error_response,
    error_response, service_unavailable_response, 
    agent_success_response, agent_error_response,
    validation_failed_response
)
from app_config import (
    USER_MAX_CONVERSATIONS, CONVERSATION_CONTEXT_COUNT, 
    DEFAULT_ANONYMOUS_USER, ENABLE_QUESTION_ANSWER_CACHE
)

# 创建标准 Flask 应用
app = Flask(__name__)

# 创建日志记录器
logger = get_app_logger("UnifiedApp")

# React Agent 导入
try:
    from react_agent.agent import CustomReactAgent
except ImportError:
    try:
        from test.custom_react_agent.agent import CustomReactAgent
    except ImportError:
        logger.warning("无法导入 CustomReactAgent，React Agent功能将不可用")
        CustomReactAgent = None

# 初始化核心组件
vn = create_vanna_instance()
redis_conversation_manager = RedisConversationManager()

# ==================== React Agent 全局实例管理 ====================

_react_agent_instance: Optional[Any] = None
_redis_client: Optional[redis.Redis] = None

def validate_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证请求数据，并支持从thread_id中推断user_id"""
    errors = []
    
    # 验证 question（必填）
    question = data.get('question', '')
    if not question or not question.strip():
        errors.append('问题不能为空')
    elif len(question) > 2000:
        errors.append('问题长度不能超过2000字符')
    
    # 优先获取 thread_id
    thread_id = data.get('thread_id') or data.get('conversation_id')
    
    # 获取 user_id，但暂不设置默认值
    user_id = data.get('user_id')

    # 如果没有传递 user_id，则尝试从 thread_id 中推断
    if not user_id:
        if thread_id and ':' in thread_id:
            inferred_user_id = thread_id.split(':', 1)[0]
            if inferred_user_id:
                user_id = inferred_user_id
                logger.info(f"👤 未提供user_id，从 thread_id '{thread_id}' 中推断出: '{user_id}'")
            else:
                user_id = 'guest'
        else:
            user_id = 'guest'

    # 验证 user_id 长度
    if user_id and len(user_id) > 50:
        errors.append('用户ID长度不能超过50字符')
    
    # 用户ID与会话ID一致性校验
    if thread_id:
        if ':' not in thread_id:
            errors.append('会话ID格式无效，期望格式为 user_id:timestamp')
        else:
            thread_user_id = thread_id.split(':', 1)[0]
            if thread_user_id != user_id:
                errors.append(f'会话归属验证失败：会话ID [{thread_id}] 不属于当前用户 [{user_id}]')
    
    if errors:
        raise ValueError('; '.join(errors))
    
    return {
        'question': question.strip(),
        'user_id': user_id,
        'thread_id': thread_id  # 可选，不传则自动生成新会话
    }

async def get_react_agent() -> Any:
    """获取 React Agent 实例（懒加载）"""
    global _react_agent_instance, _redis_client
    
    if _react_agent_instance is None:
        if CustomReactAgent is None:
            logger.error("❌ CustomReactAgent 未能导入，无法初始化")
            raise ImportError("CustomReactAgent 未能导入")
            
        logger.info("🚀 正在异步初始化 Custom React Agent...")
        try:
            # 设置环境变量
            os.environ['REDIS_URL'] = 'redis://localhost:6379'
            
            # 初始化共享的Redis客户端
            _redis_client = redis.from_url('redis://localhost:6379', decode_responses=True)
            await _redis_client.ping()
            logger.info("✅ Redis客户端连接成功")
            
            _react_agent_instance = await CustomReactAgent.create()
            logger.info("✅ React Agent 异步初始化完成")
        except Exception as e:
            logger.error(f"❌ React Agent 异步初始化失败: {e}")
            raise
    
    return _react_agent_instance

async def ensure_agent_ready() -> bool:
    """异步确保Agent实例可用"""
    global _react_agent_instance
    
    if _react_agent_instance is None:
        await get_react_agent()
    
    # 测试Agent是否还可用
    try:
        test_result = await _react_agent_instance.get_user_recent_conversations("__test__", 1)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Agent实例不可用: {e}")
        _react_agent_instance = None
        await get_react_agent()
        return True

def cleanup_resources():
    """清理资源"""
    global _react_agent_instance, _redis_client
    
    async def async_cleanup():
        if _react_agent_instance:
            await _react_agent_instance.close()
            logger.info("✅ React Agent 资源已清理")
        
        if _redis_client:
            await _redis_client.aclose()
            logger.info("✅ Redis客户端已关闭")
    
    try:
        asyncio.run(async_cleanup())
    except Exception as e:
        logger.error(f"清理资源失败: {e}")

atexit.register(cleanup_resources)

# ==================== 基础路由 ====================

@app.route("/")
def index():
    """根路径健康检查"""
    return jsonify({"message": "统一API服务正在运行", "version": "1.0.0"})

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    try:
        health_status = {
            "status": "healthy",
            "react_agent_initialized": _react_agent_instance is not None,
            "timestamp": datetime.now().isoformat(),
            "services": {
                "redis": redis_conversation_manager.is_available(),
                "vanna": vn is not None
            }
        }
        return jsonify(health_status), 200
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# ==================== React Agent API ====================

@app.route("/api/v0/ask_react_agent", methods=["POST"])
async def ask_react_agent():
    """异步React Agent智能问答接口"""
    global _react_agent_instance
    
    # 确保Agent已初始化
    if not await ensure_agent_ready():
        return jsonify({
            "code": 503,
            "message": "服务未就绪",
            "success": False,
            "error": "React Agent 初始化失败"
        }), 503
    
    try:
        # 获取请求数据
        try:
            data = request.get_json(force=True)
        except Exception as json_error:
            logger.warning(f"⚠️ JSON解析失败: {json_error}")
            return jsonify({
                "code": 400,
                "message": "请求格式错误",
                "success": False,
                "error": "无效的JSON格式",
                "details": str(json_error)
            }), 400
        
        if not data:
            return jsonify({
                "code": 400,
                "message": "请求参数错误",
                "success": False,
                "error": "请求体不能为空"
            }), 400
        
        # 验证请求数据
        validated_data = validate_request_data(data)
        
        logger.info(f"📨 收到React Agent请求 - User: {validated_data['user_id']}, Question: {validated_data['question'][:50]}...")
        
        # 异步调用处理
        agent_result = await _react_agent_instance.chat(
            message=validated_data['question'],
            user_id=validated_data['user_id'],
            thread_id=validated_data['thread_id']
        )
        
        if not agent_result.get("success", False):
            # Agent处理失败
            error_msg = agent_result.get("error", "React Agent处理失败")
            logger.error(f"❌ React Agent处理失败: {error_msg}")
            
            return jsonify({
                "code": 500,
                "message": "处理失败",
                "success": False,
                "error": error_msg,
                "data": {
                    "conversation_id": agent_result.get("thread_id"),
                    "user_id": validated_data['user_id'],
                    "timestamp": datetime.now().isoformat()
                }
            }), 500
        
        # Agent处理成功
        api_data = agent_result.get("api_data", {})
        
        # 构建响应数据（按照 react_agent/api.py 的正确格式）
        response_data = {
            "response": api_data.get("response", ""),
            "conversation_id": agent_result.get("thread_id"),
            "user_id": validated_data['user_id'],
            "react_agent_meta": api_data.get("react_agent_meta", {
                "thread_id": agent_result.get("thread_id"),
                "agent_version": "custom_react_v1_async"
            }),
            "timestamp": datetime.now().isoformat()
        }
        
        # 可选字段：SQL（仅当执行SQL时存在）
        if "sql" in api_data:
            response_data["sql"] = api_data["sql"]
        
        # 可选字段：records（仅当有查询结果时存在）
        if "records" in api_data:
            response_data["records"] = api_data["records"]
        
        return jsonify({
            "code": 200,
            "message": "处理成功",
            "success": True,
            "data": response_data
        }), 200
        
    except ValueError as ve:
        # 参数验证错误
        logger.warning(f"⚠️ 参数验证失败: {ve}")
        return jsonify({
            "code": 400,
            "message": "参数验证失败",
            "success": False,
            "error": str(ve)
        }), 400
        
    except Exception as e:
        logger.error(f"❌ React Agent API 异常: {e}")
        return jsonify({
            "code": 500,
            "message": "内部服务错误",
            "success": False,
            "error": "服务暂时不可用，请稍后重试"
        }), 500

# ==================== LangGraph Agent API ====================

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
            raise Exception(f"Agent模块导入失败: {str(e)}")
        except Exception as e:
            logger.critical(f"LangGraph Agent实例创建失败: {str(e)}")
            raise Exception(f"Agent初始化失败: {str(e)}")
    return citu_langraph_agent

@app.route('/api/v0/ask_agent', methods=['POST'])
def ask_agent():
    """支持对话上下文的ask_agent API"""
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)
    user_id_input = req.get("user_id", None)
    conversation_id_input = req.get("conversation_id", None)
    continue_conversation = req.get("continue_conversation", False)
    api_routing_mode = req.get("routing_mode", None)
    
    VALID_ROUTING_MODES = ["database_direct", "chat_direct", "hybrid", "llm_only"]
    
    if not question:
        return jsonify(bad_request_response(
            response_text="缺少必需参数：question",
            missing_params=["question"]
        )), 400
    
    if api_routing_mode and api_routing_mode not in VALID_ROUTING_MODES:
        return jsonify(bad_request_response(
            response_text=f"无效的routing_mode参数值: {api_routing_mode}，支持的值: {VALID_ROUTING_MODES}",
            invalid_params=["routing_mode"]
        )), 400

    try:
        # 获取登录用户ID
        login_user_id = session.get('user_id') if 'user_id' in session else None
        
        # 智能ID解析
        user_id = redis_conversation_manager.resolve_user_id(
            user_id_input, browser_session_id, request.remote_addr, login_user_id
        )
        conversation_id, conversation_status = redis_conversation_manager.resolve_conversation_id(
            user_id, conversation_id_input, continue_conversation
        )
        
        # 获取上下文
        context = redis_conversation_manager.get_context(conversation_id)
        
        # 保存用户消息
        redis_conversation_manager.save_message(conversation_id, "user", question)
        
        # 构建带上下文的问题
        if context:
            enhanced_question = f"\n[CONTEXT]\n{context}\n\n[CURRENT]\n{question}"
            logger.info(f"[AGENT_API] 使用上下文，长度: {len(context)}字符")
        else:
            enhanced_question = question
            logger.info(f"[AGENT_API] 新对话，无上下文")
        
        # Agent处理
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
            question=enhanced_question,
            session_id=browser_session_id
        ))
        
        # 处理Agent结果
        if agent_result.get("success", False):
            response_type = agent_result.get("type", "UNKNOWN")
            response_text = agent_result.get("response", "")
            sql = agent_result.get("sql")
            query_result = agent_result.get("query_result")
            summary = agent_result.get("summary")
            execution_path = agent_result.get("execution_path", [])
            classification_info = agent_result.get("classification_info", {})
            
            # 确定助手回复内容的优先级
            if response_type == "DATABASE":
                if response_text:
                    assistant_response = response_text
                elif summary:
                    assistant_response = summary
                elif query_result:
                    row_count = query_result.get("row_count", 0)
                    assistant_response = f"查询执行完成，共返回 {row_count} 条记录。"
                else:
                    assistant_response = "数据库查询已处理。"
            else:
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
            
            return jsonify(agent_success_response(
                response_type=response_type,
                response=response_text,
                sql=sql,
                records=query_result,
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
                conversation_message=conversation_status["message"]
            ))
        else:
            # 错误处理
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

# ==================== QA反馈系统API ====================

qa_feedback_manager = None

def get_qa_feedback_manager():
    """获取QA反馈管理器实例（懒加载）"""
    global qa_feedback_manager
    if qa_feedback_manager is None:
        try:
            qa_feedback_manager = QAFeedbackManager(vanna_instance=vn)
            logger.info("QA反馈管理器实例创建成功")
        except Exception as e:
            logger.critical(f"QA反馈管理器创建失败: {str(e)}")
            raise Exception(f"QA反馈管理器初始化失败: {str(e)}")
    return qa_feedback_manager

@app.route('/api/v0/qa_feedback/query', methods=['POST'])
def qa_feedback_query():
    """查询反馈记录API"""
    try:
        req = request.get_json(force=True)
        
        page = req.get('page', 1)
        page_size = req.get('page_size', 20)
        is_thumb_up = req.get('is_thumb_up')
        
        if page < 1 or page_size < 1 or page_size > 100:
            return jsonify(bad_request_response(
                response_text="参数错误"
            )), 400
        
        manager = get_qa_feedback_manager()
        records, total = manager.query_feedback(
            page=page,
            page_size=page_size,
            is_thumb_up=is_thumb_up
        )
        
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

@app.route('/api/v0/qa_feedback/delete/<int:feedback_id>', methods=['DELETE'])
def qa_feedback_delete(feedback_id):
    """删除反馈记录API"""
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

@app.route('/api/v0/qa_feedback/update/<int:feedback_id>', methods=['PUT'])
def qa_feedback_update(feedback_id):
    """更新反馈记录API"""
    try:
        req = request.get_json(force=True)
        
        allowed_fields = ['question', 'sql', 'is_thumb_up', 'user_id', 'is_in_training_data']
        update_data = {}
        
        for field in allowed_fields:
            if field in req:
                update_data[field] = req[field]
        
        if not update_data:
            return jsonify(bad_request_response(
                response_text="没有提供有效的更新字段"
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

@app.route('/api/v0/qa_feedback/add_to_training', methods=['POST'])
def qa_feedback_add_to_training():
    """将反馈记录添加到训练数据集API"""
    try:
        req = request.get_json(force=True)
        feedback_ids = req.get('feedback_ids', [])
        
        if not feedback_ids or not isinstance(feedback_ids, list):
            return jsonify(bad_request_response(
                response_text="缺少有效的反馈ID列表"
            )), 400
        
        manager = get_qa_feedback_manager()
        records = manager.get_feedback_by_ids(feedback_ids)
        
        if not records:
            return jsonify(not_found_response(
                response_text="未找到任何有效的反馈记录"
            )), 404
        
        positive_count = 0
        negative_count = 0
        successfully_trained_ids = []
        
        for record in records:
            try:
                if record['is_in_training_data']:
                    continue
                
                if record['is_thumb_up']:
                    training_id = vn.train(
                        question=record['question'], 
                        sql=record['sql']
                    )
                    positive_count += 1
                else:
                    training_id = vn.train_error_sql(
                        question=record['question'], 
                        sql=record['sql']
                    )
                    negative_count += 1
                
                successfully_trained_ids.append(record['id'])
                
            except Exception as e:
                logger.error(f"训练失败 - 反馈ID: {record['id']}, 错误: {e}")
        
        if successfully_trained_ids:
            manager.mark_training_status(successfully_trained_ids, True)
        
        return jsonify(success_response(
            response_text=f"训练数据添加完成，成功处理 {positive_count + negative_count} 条记录",
            data={
                "positive_trained": positive_count,
                "negative_trained": negative_count,
                "successfully_trained_ids": successfully_trained_ids
            }
        ))
        
    except Exception as e:
        logger.error(f"qa_feedback_add_to_training执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="添加训练数据失败，请稍后重试"
        )), 500

@app.route('/api/v0/qa_feedback/add', methods=['POST'])
def qa_feedback_add():
    """添加反馈记录API"""
    try:
        req = request.get_json(force=True)
        question = req.get('question')
        sql = req.get('sql')
        is_thumb_up = req.get('is_thumb_up')
        user_id = req.get('user_id', 'guest')
        
        if not question or not sql or is_thumb_up is None:
            return jsonify(bad_request_response(
                response_text="缺少必需参数"
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
            data={"feedback_id": feedback_id}
        ))
        
    except Exception as e:
        logger.error(f"qa_feedback_add执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建反馈记录失败，请稍后重试"
        )), 500

@app.route('/api/v0/qa_feedback/stats', methods=['GET'])
def qa_feedback_stats():
    """反馈统计API"""
    try:
        manager = get_qa_feedback_manager()
        
        all_records, total_count = manager.query_feedback(page=1, page_size=1)
        positive_records, positive_count = manager.query_feedback(page=1, page_size=1, is_thumb_up=True)
        negative_records, negative_count = manager.query_feedback(page=1, page_size=1, is_thumb_up=False)
        
        return jsonify(success_response(
            response_text="统计信息获取成功",
            data={
                "total_feedback": total_count,
                "positive_feedback": positive_count,
                "negative_feedback": negative_count,
                "positive_rate": round(positive_count / max(total_count, 1) * 100, 2)
            }
        ))
        
    except Exception as e:
        logger.error(f"qa_feedback_stats执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取统计信息失败，请稍后重试"
        )), 500

# ==================== Redis对话管理API ====================

@app.route('/api/v0/user/<user_id>/conversations', methods=['GET'])
def get_user_conversations_redis(user_id: str):
    """获取用户的对话列表"""
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

@app.route('/api/v0/conversation/<conversation_id>/messages', methods=['GET'])
def get_conversation_messages_redis(conversation_id: str):
    """获取特定对话的消息历史"""
    try:
        limit = request.args.get('limit', type=int)
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

@app.route('/api/v0/conversation_stats', methods=['GET'])
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

@app.route('/api/v0/conversation_cleanup', methods=['POST'])
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

@app.route('/api/v0/embedding_cache_stats', methods=['GET'])
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

@app.route('/api/v0/embedding_cache_cleanup', methods=['POST'])
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

# ==================== 训练数据管理API ====================

def validate_sql_syntax(sql: str) -> tuple[bool, str]:
    """SQL语法检查"""
    try:
        parsed = sqlparse.parse(sql.strip())
        
        if not parsed or not parsed[0].tokens:
            return False, "SQL语法错误：空语句"
        
        sql_upper = sql.strip().upper()
        if not any(sql_upper.startswith(keyword) for keyword in 
                  ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']):
            return False, "SQL语法错误：不是有效的SQL语句"
        
        return True, ""
    except Exception as e:
        return False, f"SQL语法错误：{str(e)}"

@app.route('/api/v0/training_data/stats', methods=['GET'])
def training_data_stats():
    """获取训练数据统计信息API"""
    try:
        training_data = vn.get_training_data()
        
        if training_data is None or training_data.empty:
            return jsonify(success_response(
                response_text="统计信息获取成功",
                data={
                    "total_count": 0,
                    "last_updated": datetime.now().isoformat()
                }
            ))
        
        total_count = len(training_data)
        
        return jsonify(success_response(
            response_text="统计信息获取成功",
            data={
                "total_count": total_count,
                "last_updated": datetime.now().isoformat()
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_stats执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="获取统计信息失败，请稍后重试"
        )), 500

@app.route('/api/v0/training_data/query', methods=['POST'])
def training_data_query():
    """分页查询训练数据API"""
    try:
        req = request.get_json(force=True)
        
        page = req.get('page', 1)
        page_size = req.get('page_size', 20)
        
        if page < 1 or page_size < 1 or page_size > 100:
            return jsonify(bad_request_response(
                response_text="参数错误"
            )), 400
        
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
                    }
                }
            ))
        
        records = training_data.to_dict(orient="records")
        total = len(records)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_data = records[start_idx:end_idx]
        total_pages = (total + page_size - 1) // page_size
        
        return jsonify(success_response(
            response_text=f"查询成功，共找到 {total} 条记录",
            data={
                "records": page_data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": end_idx < total,
                    "has_prev": page > 1
                }
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_query执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询训练数据失败，请稍后重试"
        )), 500

@app.route('/api/v0/training_data/create', methods=['POST'])
def training_data_create():
    """创建训练数据API"""
    try:
        req = request.get_json(force=True)
        data = req.get('data')
        
        if not data:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：data"
            )), 400
        
        if isinstance(data, dict):
            data_list = [data]
        elif isinstance(data, list):
            data_list = data
        else:
            return jsonify(bad_request_response(
                response_text="data字段格式错误，应为对象或数组"
            )), 400
        
        if len(data_list) > 50:
            return jsonify(bad_request_response(
                response_text="批量操作最大支持50条记录"
            )), 400
        
        results = []
        successful_count = 0
        
        for index, item in enumerate(data_list):
            try:
                training_type = item.get('training_data_type')
                
                if training_type == 'sql':
                    sql = item.get('sql')
                    if not sql:
                        raise ValueError("SQL字段是必需的")
                    
                    is_valid, error_msg = validate_sql_syntax(sql)
                    if not is_valid:
                        raise ValueError(error_msg)
                    
                    question = item.get('question')
                    if question:
                        training_id = vn.train(question=question, sql=sql)
                    else:
                        training_id = vn.train(sql=sql)
                        
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
                
                results.append({
                    "index": index,
                    "success": True,
                    "training_id": training_id,
                    "type": training_type,
                    "message": f"{training_type}训练数据创建成功"
                })
                successful_count += 1
                
            except Exception as e:
                results.append({
                    "index": index,
                    "success": False,
                    "type": item.get('training_data_type', 'unknown'),
                    "error": str(e),
                    "message": "创建失败"
                })
        
        failed_count = len(data_list) - successful_count
        
        if failed_count == 0:
            return jsonify(success_response(
                response_text="训练数据创建完成",
                data={
                    "total_requested": len(data_list),
                    "successfully_created": successful_count,
                    "failed_count": failed_count,
                    "results": results
                }
            ))
        else:
            return jsonify(error_response(
                response_text=f"训练数据创建部分成功，成功{successful_count}条，失败{failed_count}条",
                data={
                    "total_requested": len(data_list),
                    "successfully_created": successful_count,
                    "failed_count": failed_count,
                    "results": results
                }
            )), 207
        
    except Exception as e:
        logger.error(f"training_data_create执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建训练数据失败，请稍后重试"
        )), 500

@app.route('/api/v0/training_data/delete', methods=['POST'])
def training_data_delete():
    """删除训练数据API"""
    try:
        req = request.get_json(force=True)
        ids = req.get('ids', [])
        confirm = req.get('confirm', False)
        
        if not ids or not isinstance(ids, list):
            return jsonify(bad_request_response(
                response_text="缺少有效的ID列表"
            )), 400
        
        if not confirm:
            return jsonify(bad_request_response(
                response_text="删除操作需要确认，请设置confirm为true"
            )), 400
        
        if len(ids) > 50:
            return jsonify(bad_request_response(
                response_text="批量删除最大支持50条记录"
            )), 400
        
        deleted_ids = []
        failed_ids = []
        
        for training_id in ids:
            try:
                success = vn.remove_training_data(training_id)
                if success:
                    deleted_ids.append(training_id)
                else:
                    failed_ids.append(training_id)
            except Exception as e:
                failed_ids.append(training_id)
        
        failed_count = len(failed_ids)
        
        if failed_count == 0:
            return jsonify(success_response(
                response_text="训练数据删除完成",
                data={
                    "total_requested": len(ids),
                    "successfully_deleted": len(deleted_ids),
                    "failed_count": failed_count,
                    "deleted_ids": deleted_ids,
                    "failed_ids": failed_ids
                }
            ))
        else:
            return jsonify(error_response(
                response_text=f"训练数据删除部分成功，成功{len(deleted_ids)}条，失败{failed_count}条",
                data={
                    "total_requested": len(ids),
                    "successfully_deleted": len(deleted_ids),
                    "failed_count": failed_count,
                    "deleted_ids": deleted_ids,
                    "failed_ids": failed_ids
                }
            )), 207
        
    except Exception as e:
        logger.error(f"training_data_delete执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除训练数据失败，请稍后重试"
        )), 500

# ==================== 启动逻辑 ====================

def signal_handler(signum, frame):
    """信号处理器，优雅退出"""
    logger.info(f"接收到信号 {signum}，准备退出...")
    cleanup_resources()
    sys.exit(0)

if __name__ == '__main__':
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 启动统一API服务...")
    logger.info("📍 服务地址: http://localhost:8084")
    logger.info("🔗 健康检查: http://localhost:8084/health")
    logger.info("📘 React Agent API: http://localhost:8084/api/v0/ask_react_agent")
    logger.info("📘 LangGraph Agent API: http://localhost:8084/api/v0/ask_agent")
    
    # 启动标准Flask应用（支持异步路由）
    app.run(host="0.0.0.0", port=8084, debug=False, threaded=True)
