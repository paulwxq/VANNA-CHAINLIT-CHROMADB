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
from datetime import datetime, timedelta, timezone
import pytz
from typing import Optional, Dict, Any, TYPE_CHECKING, Union
import signal
from threading import Thread

if TYPE_CHECKING:
    from react_agent.agent import CustomReactAgent

# 初始化日志系统 - 必须在最前面
from core.logging import initialize_logging, get_app_logger
initialize_logging()

# 标准 Flask 导入
from flask import Flask, request, jsonify, session, send_file, Response, stream_with_context
import redis.asyncio as redis
from werkzeug.utils import secure_filename

# 导入标准化响应格式
from common.result import success_response, internal_error_response, bad_request_response

# 基础依赖
import pandas as pd
import json
import sqlparse
import tempfile
import os
import psycopg2
import re

# 项目模块导入
from core.vanna_llm_factory import create_vanna_instance
from common.redis_conversation_manager import RedisConversationManager
from common.qa_feedback_manager import QAFeedbackManager
# Data Pipeline 相关导入 - 从 citu_app.py 迁移
from data_pipeline.api.simple_workflow import SimpleWorkflowManager, SimpleWorkflowExecutor
from data_pipeline.api.simple_file_manager import SimpleFileManager
from data_pipeline.api.table_inspector_api import TableInspectorAPI
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
    from react_agent.enhanced_redis_api import get_conversation_detail_from_redis
except ImportError:
    try:
        from test.custom_react_agent.agent import CustomReactAgent
        from test.custom_react_agent.enhanced_redis_api import get_conversation_detail_from_redis
    except ImportError:
        logger.warning("无法导入 CustomReactAgent，React Agent功能将不可用")
        CustomReactAgent = None
        get_conversation_detail_from_redis = None

# 初始化核心组件
vn = create_vanna_instance()
redis_conversation_manager = RedisConversationManager()

# ==================== React Agent 全局实例管理 ====================

_react_agent_instance: Optional[Any] = None
_redis_client: Optional[redis.Redis] = None

def _format_timestamp_to_china_time(timestamp_str):
    """将ISO时间戳转换为中国时区的指定格式"""
    if not timestamp_str:
        return None
    try:
        # 解析ISO时间戳
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # 转换为中国时区
        china_tz = pytz.timezone('Asia/Shanghai')
        china_dt = dt.astimezone(china_tz)
        # 格式化为指定格式
        return china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # 保留3位毫秒
    except Exception as e:
        logger.warning(f"⚠️ 时间格式化失败: {e}")
        return timestamp_str

def _parse_conversation_created_time(conversation_id: str) -> Optional[str]:
    """从conversation_id解析创建时间并转换为中国时区格式"""
    try:
        # conversation_id格式: "wang10:20250717211620915"
        if ':' not in conversation_id:
            return None
        
        parts = conversation_id.split(':')
        if len(parts) < 2:
            return None
        
        timestamp_str = parts[1]  # "20250717211620915"
        
        # 解析时间戳: YYYYMMDDHHMMSSMMM (17位)
        if len(timestamp_str) != 17:
            logger.warning(f"⚠️ conversation_id时间戳长度不正确: {timestamp_str}")
            return None
        
        year = timestamp_str[:4]
        month = timestamp_str[4:6]
        day = timestamp_str[6:8]
        hour = timestamp_str[8:10]
        minute = timestamp_str[10:12]
        second = timestamp_str[12:14]
        millisecond = timestamp_str[14:17]
        
        # 构造datetime对象
        dt = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
            int(millisecond) * 1000  # 毫秒转微秒
        )
        
        # 转换为中国时区
        china_tz = pytz.timezone('Asia/Shanghai')
        # 假设原始时间戳是中国时区
        china_dt = china_tz.localize(dt)
        
        # 格式化为要求的格式
        formatted_time = china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # 保留3位毫秒
        return formatted_time
        
    except Exception as e:
        logger.warning(f"⚠️ 解析conversation_id时间戳失败: {e}")
        return None

def _get_conversation_updated_time(redis_client, thread_id: str) -> Optional[str]:
    """获取对话的最后更新时间（从Redis checkpoint数据中的ts字段）"""
    try:
        # 扫描该thread的所有checkpoint keys
        pattern = f"checkpoint:{thread_id}:*"
        
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        if not keys:
            return None
        
        # 获取最新的checkpoint（按key排序，最大的是最新的）
        latest_key = max(keys)
        
        # 检查key类型并获取数据
        key_type = redis_client.type(latest_key)
        
        data = None
        if key_type == 'string':
            data = redis_client.get(latest_key)
        elif key_type == 'ReJSON-RL':
            # RedisJSON类型
            try:
                data = redis_client.execute_command('JSON.GET', latest_key)
            except Exception as json_error:
                logger.error(f"❌ JSON.GET失败: {json_error}")
                return None
        else:
            return None
        
        if not data:
            return None
        
        # 解析JSON数据
        try:
            checkpoint_data = json.loads(data)
        except json.JSONDecodeError:
            return None
        
        # 检查checkpoint中的ts字段
        if ('checkpoint' in checkpoint_data and 
            isinstance(checkpoint_data['checkpoint'], dict) and 
            'ts' in checkpoint_data['checkpoint']):
            
            ts_value = checkpoint_data['checkpoint']['ts']
            
            # 解析ts字段（应该是ISO格式的时间戳）
            if isinstance(ts_value, str):
                try:
                    dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                    china_tz = pytz.timezone('Asia/Shanghai')
                    china_dt = dt.astimezone(china_tz)
                    formatted_time = china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    return formatted_time
                except Exception:
                    pass
        
        return None
        
    except Exception as e:
        logger.warning(f"⚠️ 获取对话更新时间失败: {e}")
        return None

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

def get_user_conversations_simple_sync(user_id: str, limit: int = 10):
    """直接从Redis获取用户对话，测试版本"""
    import redis
    import json
    
    try:
        # 创建Redis连接
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        
        # 扫描用户的checkpoint keys
        pattern = f"checkpoint:{user_id}:*"
        logger.info(f"🔍 扫描模式: {pattern}")
        
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        logger.info(f"📋 找到 {len(keys)} 个keys")
        
        # 解析thread信息
        thread_data = {}
        for key in keys:
            try:
                parts = key.split(':')
                if len(parts) >= 4:
                    thread_id = f"{parts[1]}:{parts[2]}"  # user_id:timestamp
                    timestamp = parts[2]
                    
                    if thread_id not in thread_data:
                        thread_data[thread_id] = {
                            "thread_id": thread_id,
                            "timestamp": timestamp,
                            "keys": []
                        }
                    thread_data[thread_id]["keys"].append(key)
            except Exception as e:
                logger.warning(f"解析key失败 {key}: {e}")
                continue
        
        logger.info(f"📊 找到 {len(thread_data)} 个thread")
        
        # 按时间戳排序
        sorted_threads = sorted(
            thread_data.values(),
            key=lambda x: x["timestamp"],
            reverse=True
        )[:limit]
        
        # 获取每个thread的详细信息
        conversations = []
        for thread_info in sorted_threads:
            try:
                thread_id = thread_info["thread_id"]
                
                # 获取最新的checkpoint数据
                latest_key = max(thread_info["keys"])
                
                # 先检查key的数据类型
                key_type = redis_client.type(latest_key)
                logger.info(f"🔍 Key {latest_key} 的类型: {key_type}")
                
                data = None
                if key_type == 'string':
                    data = redis_client.get(latest_key)
                elif key_type == 'hash':
                    # 如果是hash类型，获取所有字段
                    hash_data = redis_client.hgetall(latest_key)
                    logger.info(f"🔍 Hash字段: {list(hash_data.keys())}")
                    # 尝试获取可能的数据字段
                    for field in ['data', 'state', 'value', 'checkpoint']:
                        if field in hash_data:
                            data = hash_data[field]
                            break
                    if not data and hash_data:
                        # 如果没找到预期字段，取第一个值试试
                        data = list(hash_data.values())[0]
                elif key_type == 'list':
                    # 如果是list类型，获取最后一个元素
                    data = redis_client.lindex(latest_key, -1)
                elif key_type == 'ReJSON-RL':
                    # 这是RedisJSON类型，使用JSON.GET命令
                    logger.info(f"🔍 使用JSON.GET获取RedisJSON数据")
                    try:
                        # 使用JSON.GET命令获取整个JSON对象
                        json_data = redis_client.execute_command('JSON.GET', latest_key)
                        if json_data:
                            data = json_data  # JSON.GET返回的就是JSON字符串
                            logger.info(f"🔍 JSON数据长度: {len(data)} 字符")
                        else:
                            logger.warning(f"⚠️ JSON.GET 返回空数据")
                            continue
                    except Exception as json_error:
                        logger.error(f"❌ JSON.GET 失败: {json_error}")
                        continue
                else:
                    logger.warning(f"⚠️ 未知的key类型: {key_type}")
                    continue
                
                if data:
                    try:
                        checkpoint_data = json.loads(data)
                        
                        # 调试：查看JSON数据结构
                        logger.info(f"🔍 JSON顶级keys: {list(checkpoint_data.keys())}")
                        
                        # 根据您提供的JSON结构，消息在 checkpoint.channel_values.messages
                        messages = []
                        
                        # 首先检查是否有checkpoint字段
                        if 'checkpoint' in checkpoint_data:
                            checkpoint = checkpoint_data['checkpoint']
                            if isinstance(checkpoint, dict) and 'channel_values' in checkpoint:
                                channel_values = checkpoint['channel_values']
                                if isinstance(channel_values, dict) and 'messages' in channel_values:
                                    messages = channel_values['messages']
                                    logger.info(f"🔍 找到messages: {len(messages)} 条消息")
                        
                        # 如果没有checkpoint字段，尝试直接在channel_values
                        if not messages and 'channel_values' in checkpoint_data:
                            channel_values = checkpoint_data['channel_values']
                            if isinstance(channel_values, dict) and 'messages' in channel_values:
                                messages = channel_values['messages']
                                logger.info(f"🔍 找到messages(直接路径): {len(messages)} 条消息")
                        
                        # 生成对话预览
                        preview = "空对话"
                        if messages:
                            for msg in messages:
                                # 处理LangChain消息格式：{"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", "HumanMessage"], "kwargs": {"content": "...", "type": "human"}}
                                if isinstance(msg, dict):
                                    # 检查是否是LangChain格式的HumanMessage
                                    if (msg.get('lc') == 1 and 
                                        msg.get('type') == 'constructor' and 
                                        'id' in msg and 
                                        isinstance(msg['id'], list) and 
                                        len(msg['id']) >= 4 and
                                        msg['id'][3] == 'HumanMessage' and
                                        'kwargs' in msg):
                                        
                                        kwargs = msg['kwargs']
                                        if kwargs.get('type') == 'human' and 'content' in kwargs:
                                            content = str(kwargs['content'])
                                            preview = content[:50] + "..." if len(content) > 50 else content
                                            break
                                    # 兼容其他格式
                                    elif msg.get('type') == 'human' and 'content' in msg:
                                        content = str(msg['content'])
                                        preview = content[:50] + "..." if len(content) > 50 else content
                                        break
                        
                        # 解析时间戳
                        created_at = _parse_conversation_created_time(thread_id)
                        updated_at = _get_conversation_updated_time(redis_client, thread_id)
                        
                        # 如果无法获取updated_at，使用created_at作为备选
                        if not updated_at:
                            updated_at = created_at
                        
                        conversations.append({
                            "conversation_id": thread_id,  # thread_id -> conversation_id
                            "user_id": user_id,
                            "message_count": len(messages),
                            "conversation_title": preview,  # conversation_preview -> conversation_title
                            "created_at": created_at,
                            "updated_at": updated_at
                        })
                        
                    except json.JSONDecodeError:
                        logger.error(f"❌ JSON解析失败，数据类型: {type(data)}, 长度: {len(str(data))}")
                        logger.error(f"❌ 数据开头: {str(data)[:200]}...")
                        continue
                    
            except Exception as e:
                logger.error(f"处理thread {thread_info['thread_id']} 失败: {e}")
                continue
        
        redis_client.close()
        logger.info(f"✅ 返回 {len(conversations)} 个对话")
        return conversations
        
    except Exception as e:
        logger.error(f"❌ Redis查询失败: {e}")
        return []

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
    """异步React Agent智能问答接口（从 custom_react_agent 迁移，原路由：/api/chat）"""
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
                "error": "无效的JSON格式，请检查请求体中是否存在语法错误（如多余的逗号、引号不匹配等）",
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
            
            # 检查是否建议重试
            retry_suggested = agent_result.get("retry_suggested", False)
            error_code = 503 if retry_suggested else 500
            message = "服务暂时不可用，请稍后重试" if retry_suggested else "处理失败"
            
            return jsonify({
                "code": error_code,
                "message": message,
                "success": False,
                "error": error_msg,
                "retry_suggested": retry_suggested,
                "data": {
                    "conversation_id": agent_result.get("thread_id"),
                    "user_id": validated_data['user_id'],
                    "timestamp": datetime.now().isoformat()
                }
            }), error_code
        
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
        
        # 获取上下文和上下文类型（提前到缓存检查之前）
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
        
        # 检查缓存（新逻辑：放宽使用条件，严控存储条件）
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
                response=cached_answer.get("response", ""),
                sql=cached_answer.get("sql"),
                records=cached_answer.get("query_result"),
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
        
        # 保存用户消息
        redis_conversation_manager.save_message(conversation_id, "user", question)
        
        # 构建带上下文的问题
        if context:
            enhanced_question = f"\n[CONTEXT]\n{context}\n\n[CURRENT]\n{question}"
            logger.info(f"[AGENT_API] 使用上下文，长度: {len(context)}字符")
        else:
            enhanced_question = question
            logger.info(f"[AGENT_API] 新对话，无上下文")
        
        # 确定最终使用的路由模式（优先级逻辑）
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
            question=enhanced_question,  # 使用增强后的问题
            session_id=browser_session_id,
            context_type=context_type,  # 传递上下文类型
            routing_mode=effective_routing_mode  # 新增：传递路由模式
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
            
            # 缓存成功的答案（新逻辑：只缓存无上下文的问答）
            # 直接缓存agent_result，它已经包含所有需要的字段
            redis_conversation_manager.cache_answer(question, agent_result, context)
            
            # 使用agent_success_response的正确方式
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
                conversation_message=conversation_status["message"],
                requested_conversation_id=conversation_status.get("requested_id"),
                routing_mode_used=effective_routing_mode,  # 新增：实际使用的路由模式
                routing_mode_source="api" if api_routing_mode else "config"  # 新增：路由模式来源
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

@app.route('/api/v0/qa_feedback/add_to_training', methods=['POST'])
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

@app.route('/api/v0/qa_feedback/add', methods=['POST'])
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

@app.route('/api/v0/qa_feedback/stats', methods=['GET'])
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

def paginate_data(data_list: list, page: int, page_size: int):
    """分页算法"""
    total = len(data_list)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_data = data_list[start_idx:end_idx]
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "data": page_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
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

@app.route('/api/v0/training_data/query', methods=['POST'])
def training_data_query():
    """分页查询训练数据API - 支持类型筛选、搜索和排序功能"""
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

@app.route('/api/v0/training_data/create', methods=['POST'])
def training_data_create():
    """创建训练数据API - 支持单条和批量创建，支持四种数据类型"""
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
        
        # 根据实际执行结果决定响应状态
        failed_count = len(data_list) - successful_count
        
        if failed_count == 0:
            # 全部成功
            return jsonify(success_response(
                response_text="训练数据创建完成",
                data={
                    "total_requested": len(data_list),
                    "successfully_created": successful_count,
                    "failed_count": failed_count,
                    "results": results,
                    "summary": type_summary,
                    "current_total_count": current_total
                }
            ))
        elif successful_count == 0:
            # 全部失败
            return jsonify(error_response(
                response_text="训练数据创建失败",
                data={
                    "total_requested": len(data_list),
                    "successfully_created": successful_count,
                    "failed_count": failed_count,
                    "results": results,
                    "summary": type_summary,
                    "current_total_count": current_total
                }
            )), 400
        else:
            # 部分成功，部分失败
            return jsonify(error_response(
                response_text=f"训练数据创建部分成功，成功{successful_count}条，失败{failed_count}条",
                data={
                    "total_requested": len(data_list),
                    "successfully_created": successful_count,
                    "failed_count": failed_count,
                    "results": results,
                    "summary": type_summary,
                    "current_total_count": current_total
                }
            )), 207
        
    except Exception as e:
        logger.error(f"training_data_create执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="创建训练数据失败，请稍后重试"
        )), 500

@app.route('/api/v0/training_data/delete', methods=['POST'])
def training_data_delete():
    """删除训练数据API - 支持批量删除"""
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
        
        # 根据实际执行结果决定响应状态
        failed_count = len(failed_ids)
        
        if failed_count == 0:
            # 全部成功
            return jsonify(success_response(
                response_text="训练数据删除完成",
                data={
                    "total_requested": len(ids),
                    "successfully_deleted": len(deleted_ids),
                    "failed_count": failed_count,
                    "deleted_ids": deleted_ids,
                    "failed_ids": failed_ids,
                    "failed_details": failed_details,
                    "current_total_count": current_total
                }
            ))
        elif len(deleted_ids) == 0:
            # 全部失败
            return jsonify(error_response(
                response_text="训练数据删除失败",
                data={
                    "total_requested": len(ids),
                    "successfully_deleted": len(deleted_ids),
                    "failed_count": failed_count,
                    "deleted_ids": deleted_ids,
                    "failed_ids": failed_ids,
                    "failed_details": failed_details,
                    "current_total_count": current_total
                }
            )), 400
        else:
            # 部分成功，部分失败
            return jsonify(error_response(
                response_text=f"训练数据删除部分成功，成功{len(deleted_ids)}条，失败{failed_count}条",
                data={
                    "total_requested": len(ids),
                    "successfully_deleted": len(deleted_ids),
                    "failed_count": failed_count,
                    "deleted_ids": deleted_ids,
                    "failed_ids": failed_ids,
                    "failed_details": failed_details,
                    "current_total_count": current_total
                }
            )), 207
        
    except Exception as e:
        logger.error(f"training_data_delete执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除训练数据失败，请稍后重试"
        )), 500

@app.route('/api/v0/training_data/update', methods=['POST'])
def training_data_update():
    """更新训练数据API - 支持单条更新，采用先删除后插入策略"""
    try:
        req = request.get_json(force=True)
        
        # 1. 参数验证
        original_id = req.get('id')
        if not original_id:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：id",
                missing_params=["id"]
            )), 400
        
        training_type = req.get('training_data_type')
        if not training_type:
            return jsonify(bad_request_response(
                response_text="缺少必需参数：training_data_type",
                missing_params=["training_data_type"]
            )), 400
        
        # 2. 先删除原始记录
        try:
            success = vn.remove_training_data(original_id)
            if not success:
                return jsonify(bad_request_response(
                    response_text=f"原始记录 {original_id} 不存在或删除失败"
                )), 400
        except Exception as e:
            return jsonify(internal_error_response(
                response_text=f"删除原始记录失败: {str(e)}"
            )), 500
        
        # 3. 根据类型验证和准备新数据
        try:
            if training_type == 'sql':
                sql = req.get('sql')
                if not sql:
                    return jsonify(bad_request_response(
                        response_text="SQL字段是必需的",
                        missing_params=["sql"]
                    )), 400
                
                # SQL语法检查
                is_valid, error_msg = validate_sql_syntax(sql)
                if not is_valid:
                    return jsonify(bad_request_response(
                        response_text=f"SQL语法错误: {error_msg}"
                    )), 400
                
                question = req.get('question')
                if question:
                    training_id = vn.train(question=question, sql=sql)
                else:
                    training_id = vn.train(sql=sql)
                    
            elif training_type == 'error_sql':
                question = req.get('question')
                sql = req.get('sql')
                if not question or not sql:
                    return jsonify(bad_request_response(
                        response_text="question和sql字段都是必需的",
                        missing_params=["question", "sql"]
                    )), 400
                training_id = vn.train_error_sql(question=question, sql=sql)
                
            elif training_type == 'documentation':
                content = req.get('content')
                if not content:
                    return jsonify(bad_request_response(
                        response_text="content字段是必需的",
                        missing_params=["content"]
                    )), 400
                training_id = vn.train(documentation=content)
                
            elif training_type == 'ddl':
                ddl = req.get('ddl')
                if not ddl:
                    return jsonify(bad_request_response(
                        response_text="ddl字段是必需的",
                        missing_params=["ddl"]
                    )), 400
                training_id = vn.train(ddl=ddl)
                
            else:
                return jsonify(bad_request_response(
                    response_text=f"不支持的训练数据类型: {training_type}"
                )), 400
                
        except Exception as e:
            return jsonify(internal_error_response(
                response_text=f"创建新训练数据失败: {str(e)}"
            )), 500
        
        # 4. 获取更新后的总记录数
        current_total = get_total_training_count()
        
        return jsonify(success_response(
            response_text="训练数据更新成功",
            data={
                "original_id": original_id,
                "new_training_id": training_id,
                "type": training_type,
                "current_total_count": current_total
            }
        ))
        
    except Exception as e:
        logger.error(f"training_data_update执行失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="更新训练数据失败，请稍后重试"
        )), 500

# 导入现有的专业训练函数
from data_pipeline.trainer.run_training import (
    train_ddl_statements,
    train_documentation_blocks, 
    train_json_question_sql_pairs,
    train_formatted_question_sql_pairs,
    train_sql_examples
)

def get_allowed_extensions(file_type: str) -> list:
    """根据文件类型返回允许的扩展名"""
    type_specific_extensions = {
        'ddl': ['ddl', 'sql', 'txt', ''],  # 支持无扩展名
        'markdown': ['md', 'markdown'],    # 不支持无扩展名
        'sql_pair_json': ['json', 'txt', ''],  # 支持无扩展名
        'sql_pair': ['sql', 'txt', ''],   # 支持无扩展名
        'sql': ['sql', 'txt', '']         # 支持无扩展名
    }
    
    return type_specific_extensions.get(file_type, [])

def validate_file_content(content: str, file_type: str) -> dict:
    """验证文件内容格式"""
    try:
        if file_type == 'ddl':
            # 检查是否包含CREATE语句
            if not re.search(r'\bCREATE\b', content, re.IGNORECASE):
                return {'valid': False, 'error': '文件内容不符合DDL格式，必须包含CREATE语句'}
            
        elif file_type == 'markdown':
            # 检查是否包含##标题
            if '##' not in content:
                return {'valid': False, 'error': '文件内容不符合Markdown格式，必须包含##标题'}
            
        elif file_type == 'sql_pair_json':
            # 检查是否为有效JSON
            try:
                data = json.loads(content)
                if not isinstance(data, list) or not data:
                    return {'valid': False, 'error': '文件内容不符合JSON问答对格式，必须是非空数组'}
                
                # 检查是否包含question和sql字段
                for item in data:
                    if not isinstance(item, dict):
                        return {'valid': False, 'error': '文件内容不符合JSON问答对格式，数组元素必须是对象'}
                    
                    has_question = any(key.lower() == 'question' for key in item.keys())
                    has_sql = any(key.lower() == 'sql' for key in item.keys())
                    
                    if not has_question or not has_sql:
                        return {'valid': False, 'error': '文件内容不符合JSON问答对格式，必须包含question和sql字段'}
                        
            except json.JSONDecodeError:
                return {'valid': False, 'error': '文件内容不符合JSON问答对格式，JSON格式错误'}
            
        elif file_type == 'sql_pair':
            # 检查是否包含Question:和SQL:
            if not re.search(r'\bQuestion\s*:', content, re.IGNORECASE):
                return {'valid': False, 'error': '文件内容不符合问答对格式，必须包含Question:'}
            if not re.search(r'\bSQL\s*:', content, re.IGNORECASE):
                return {'valid': False, 'error': '文件内容不符合问答对格式，必须包含SQL:'}
            
        elif file_type == 'sql':
            # 检查是否包含;分隔符
            if ';' not in content:
                return {'valid': False, 'error': '文件内容不符合SQL格式，必须包含;分隔符'}
        
        return {'valid': True}
        
    except Exception as e:
        return {'valid': False, 'error': f'文件内容验证失败: {str(e)}'}

@app.route('/api/v0/training_data/upload', methods=['POST'])
def upload_training_data():
    """上传训练数据文件API - 支持多种文件格式的自动解析和导入"""
    try:
        # 1. 参数验证
        if 'file' not in request.files:
            return jsonify(bad_request_response("未提供文件"))
        
        file = request.files['file']
        if file.filename == '':
            return jsonify(bad_request_response("未选择文件"))
        
        # 获取file_type参数
        file_type = request.form.get('file_type')
        if not file_type:
            return jsonify(bad_request_response("缺少必需参数：file_type"))
        
        # 验证file_type参数
        valid_file_types = ['ddl', 'markdown', 'sql_pair_json', 'sql_pair', 'sql']
        if file_type not in valid_file_types:
            return jsonify(bad_request_response(f"不支持的文件类型：{file_type}，支持的类型：{', '.join(valid_file_types)}"))
        
        # 2. 文件大小验证 (500KB)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 500 * 1024:  # 500KB
            return jsonify(bad_request_response("文件大小不能超过500KB"))
        
        # 3. 验证文件扩展名（基于file_type）
        filename = secure_filename(file.filename)
        allowed_extensions = get_allowed_extensions(file_type)
        file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        if file_ext not in allowed_extensions:
            # 构建友好的错误信息
            non_empty_extensions = [ext for ext in allowed_extensions if ext]
            if '' in allowed_extensions:
                ext_message = f"{', '.join(non_empty_extensions)} 或无扩展名"
            else:
                ext_message = ', '.join(non_empty_extensions)
            return jsonify(bad_request_response(f"文件类型 {file_type} 不支持的文件扩展名：{file_ext}，支持的扩展名：{ext_message}"))
        
        # 4. 读取文件内容并验证格式
        file.seek(0)
        content = file.read().decode('utf-8')
        
        # 格式验证
        validation_result = validate_file_content(content, file_type)
        if not validation_result['valid']:
            return jsonify(bad_request_response(validation_result['error']))
        
        # 5. 创建临时文件（复用现有函数需要文件路径）
        temp_file_path = None
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp', encoding='utf-8') as tmp_file:
                tmp_file.write(content)
                temp_file_path = tmp_file.name
            
            # 6. 根据文件类型调用现有的训练函数
            if file_type == 'ddl':
                train_ddl_statements(temp_file_path)
                
            elif file_type == 'markdown':
                train_documentation_blocks(temp_file_path)
                
            elif file_type == 'sql_pair_json':
                train_json_question_sql_pairs(temp_file_path)
                
            elif file_type == 'sql_pair':
                train_formatted_question_sql_pairs(temp_file_path)
                
            elif file_type == 'sql':
                train_sql_examples(temp_file_path)
            
            return jsonify(success_response(
                response_text=f"文件上传并训练成功：{filename}",
                data={
                    "filename": filename,
                    "file_type": file_type,
                    "file_size": file_size,
                    "status": "completed"
                }
            ))
            
        except Exception as e:
            logger.error(f"训练失败: {str(e)}")
            return jsonify(internal_error_response(f"训练失败: {str(e)}"))
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {str(e)}")
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        return jsonify(internal_error_response(f"文件上传失败: {str(e)}"))

def get_db_connection():
    """获取数据库连接"""
    try:
        from app_config import PGVECTOR_CONFIG
        return psycopg2.connect(**PGVECTOR_CONFIG)
    except Exception as e:
        logger.error(f"数据库连接失败: {str(e)}")
        raise

def get_db_connection_for_transaction():
    """获取用于事务操作的数据库连接（非自动提交模式）"""
    try:
        from app_config import PGVECTOR_CONFIG
        conn = psycopg2.connect(**PGVECTOR_CONFIG)
        conn.autocommit = False  # 设置为非自动提交模式，允许手动控制事务
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {str(e)}")
        raise

@app.route('/api/v0/training_data/combine', methods=['POST'])
def combine_training_data():
    """合并训练数据API - 支持合并重复记录"""
    try:
        # 1. 参数验证
        data = request.get_json()
        if not data:
            return jsonify(bad_request_response("请求体不能为空"))
        
        collection_names = data.get('collection_names', [])
        if not collection_names or not isinstance(collection_names, list):
            return jsonify(bad_request_response("collection_names 参数必须是非空数组"))
        
        # 验证集合名称
        valid_collections = ['sql', 'ddl', 'documentation', 'error_sql']
        invalid_collections = [name for name in collection_names if name not in valid_collections]
        if invalid_collections:
            return jsonify(bad_request_response(f"不支持的集合名称: {invalid_collections}"))
        
        dry_run = data.get('dry_run', True)
        keep_strategy = data.get('keep_strategy', 'first')
        
        if keep_strategy not in ['first', 'last', 'by_metadata_time']:
            return jsonify(bad_request_response("keep_strategy 必须是 'first', 'last' 或 'by_metadata_time'"))
        
        # 2. 获取数据库连接（用于事务操作）
        conn = get_db_connection_for_transaction()
        cursor = conn.cursor()
        
        # 3. 查找重复记录
        duplicate_groups = []
        total_before = 0
        total_duplicates = 0
        collections_stats = {}
        
        for collection_name in collection_names:
            # 获取集合ID
            cursor.execute(
                "SELECT uuid FROM langchain_pg_collection WHERE name = %s",
                (collection_name,)
            )
            collection_result = cursor.fetchone()
            if not collection_result:
                continue
            
            collection_id = collection_result[0]
            
            # 统计该集合的记录数
            cursor.execute(
                "SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = %s",
                (collection_id,)
            )
            collection_before = cursor.fetchone()[0]
            total_before += collection_before
            
            # 查找重复记录
            if keep_strategy in ['first', 'last']:
                order_by = "id"
            else:
                order_by = "COALESCE((cmetadata->>'createdat')::timestamp, '1970-01-01'::timestamp) DESC, id"
            
            cursor.execute(f"""
                SELECT document, COUNT(*) as duplicate_count, 
                       array_agg(id ORDER BY {order_by}) as record_ids
                FROM langchain_pg_embedding 
                WHERE collection_id = %s 
                GROUP BY document 
                HAVING COUNT(*) > 1
            """, (collection_id,))
            
            collection_duplicates = 0
            for row in cursor.fetchall():
                document_content, duplicate_count, record_ids = row
                collection_duplicates += duplicate_count - 1  # 减去要保留的一条
                
                # 根据保留策略选择要保留的记录
                if keep_strategy == 'first':
                    keep_id = record_ids[0]
                    remove_ids = record_ids[1:]
                elif keep_strategy == 'last':
                    keep_id = record_ids[-1]
                    remove_ids = record_ids[:-1]
                else:  # by_metadata_time
                    keep_id = record_ids[0]  # 已经按时间排序
                    remove_ids = record_ids[1:]
                
                duplicate_groups.append({
                    "collection_name": collection_name,
                    "document_content": document_content[:100] + "..." if len(document_content) > 100 else document_content,
                    "duplicate_count": duplicate_count,
                    "kept_record_id" if not dry_run else "records_to_keep": keep_id,
                    "removed_record_ids" if not dry_run else "records_to_remove": remove_ids
                })
            
            total_duplicates += collection_duplicates
            collections_stats[collection_name] = {
                "before": collection_before,
                "after": collection_before - collection_duplicates,
                "duplicates_removed" if not dry_run else "duplicates_to_remove": collection_duplicates
            }
        
        # 4. 执行合并操作（如果不是dry_run）
        if not dry_run:
            try:
                # 连接已经设置为非自动提交模式，直接开始事务
                for group in duplicate_groups:
                    remove_ids = group["removed_record_ids"]
                    if remove_ids:
                        cursor.execute(
                            "DELETE FROM langchain_pg_embedding WHERE id = ANY(%s)",
                            (remove_ids,)
                        )
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                return jsonify(internal_error_response(f"合并操作失败: {str(e)}"))
        
        # 5. 构建响应
        total_after = total_before - total_duplicates
        
        summary = {
            "total_records_before": total_before,
            "total_records_after": total_after,
            "duplicates_removed" if not dry_run else "duplicates_to_remove": total_duplicates,
            "collections_stats": collections_stats
        }
        
        if dry_run:
            response_text = f"发现 {total_duplicates} 条重复记录，预计删除后将从 {total_before} 条减少到 {total_after} 条记录"
            data_key = "duplicate_groups"
        else:
            response_text = f"成功合并重复记录，删除了 {total_duplicates} 条重复记录，从 {total_before} 条减少到 {total_after} 条记录"
            data_key = "merged_groups"
        
        return jsonify(success_response(
            response_text=response_text,
            data={
                "dry_run": dry_run,
                "collections_processed": collection_names,
                "summary": summary,
                data_key: duplicate_groups
            }
        ))
        
    except Exception as e:
        return jsonify(internal_error_response(f"合并操作失败: {str(e)}"))
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# ==================== React Agent 扩展API ====================

@app.route('/api/v0/react/users/<user_id>/conversations', methods=['GET'])
async def get_user_conversations_react(user_id: str):
    """异步获取用户的聊天记录列表（从 custom_react_agent 迁移）"""
    global _react_agent_instance
    
    try:
        # 获取查询参数
        limit = request.args.get('limit', 10, type=int)
        
        # 限制limit的范围
        limit = max(1, min(limit, 50))  # 限制在1-50之间
        
        logger.info(f"📋 异步获取用户 {user_id} 的对话列表，限制 {limit} 条")
        
        # 确保Agent可用
        if not await ensure_agent_ready():
            return jsonify(service_unavailable_response(
                response_text="Agent 未就绪"
            )), 503
        
        # 直接调用异步方法
        conversations = await _react_agent_instance.get_user_recent_conversations(user_id, limit)
        
        return jsonify(success_response(
            response_text="获取用户对话列表成功",
            data={
                "user_id": user_id,
                "conversations": conversations,
                "total_count": len(conversations),
                "limit": limit
            }
        )), 200
        
    except Exception as e:
        logger.error(f"❌ 异步获取用户 {user_id} 对话列表失败: {e}")
        return jsonify(internal_error_response(
            response_text=f"获取用户对话列表失败: {str(e)}"
        )), 500

@app.route('/api/v0/react/conversations/<thread_id>', methods=['GET'])
async def get_user_conversation_detail_react(thread_id: str):
    """异步获取特定对话的详细历史（从 custom_react_agent 迁移）"""
    global _react_agent_instance
    
    try:
        # 从thread_id中提取user_id
        user_id = thread_id.split(':')[0] if ':' in thread_id else 'unknown'
        
        logger.info(f"📖 异步获取用户 {user_id} 的对话 {thread_id} 详情")
        
        # 确保Agent可用
        if not await ensure_agent_ready():
            return jsonify(service_unavailable_response(
                response_text="Agent 未就绪"
            )), 503
        
        # 获取查询参数
        include_tools = request.args.get('include_tools', 'false').lower() == 'true'
        
        # 直接调用异步方法
        conversation_data = await _react_agent_instance.get_conversation_history(thread_id, include_tools=include_tools)
        messages = conversation_data.get("messages", [])
        
        logger.info(f"✅ 异步成功获取对话历史，消息数量: {len(messages)}")
        
        if not messages:
            return jsonify(not_found_response(
                response_text=f"未找到对话 {thread_id}"
            )), 404
        
        # 格式化消息
        formatted_messages = []
        for msg in messages:
            formatted_msg = {
                "message_id": msg["id"],  # id -> message_id
                "role": msg["type"],      # type -> role
                "content": msg["content"],
                "timestamp": _format_timestamp_to_china_time(msg["timestamp"])  # 转换为中国时区
            }
            formatted_messages.append(formatted_msg)
        
        return jsonify(success_response(
            response_text="获取对话详情成功",
            data={
                "user_id": user_id,
                "thread_id": thread_id,
                "conversation_id": thread_id,  # 新增conversation_id字段
                "message_count": len(formatted_messages),
                "messages": formatted_messages,
                "created_at": conversation_data.get("thread_created_at"),  # 已经包含毫秒
                "total_checkpoints": conversation_data.get("total_checkpoints", 0)
            }
        )), 200
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 异步获取对话 {thread_id} 详情失败: {e}")
        logger.error(f"❌ 详细错误信息: {traceback.format_exc()}")
        return jsonify(internal_error_response(
            response_text=f"获取对话详情失败: {str(e)}"
        )), 500

@app.route('/api/test/redis', methods=['GET'])
def test_redis_connection():
    """测试Redis连接和基本查询（从 custom_react_agent 迁移）"""
    try:
        import redis
        
        # 创建Redis连接
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        
        # 扫描checkpoint keys
        pattern = "checkpoint:*"
        keys = []
        cursor = 0
        count = 0
        
        while True:
            cursor, batch = r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            count += len(batch)
            if cursor == 0 or count > 500:  # 限制扫描数量
                break
        
        # 统计用户
        users = {}
        for key in keys:
            try:
                parts = key.split(':')
                if len(parts) >= 2:
                    user_id = parts[1]
                    users[user_id] = users.get(user_id, 0) + 1
            except:
                continue
        
        r.close()
        
        return jsonify({
            "success": True,
            "data": {
                "redis_connected": True,
                "total_checkpoint_keys": len(keys),
                "users_found": list(users.keys()),
                "user_key_counts": users,
                "sample_keys": keys[:5] if keys else []
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Redis测试失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/v0/react/direct/users/<user_id>/conversations', methods=['GET'])
def test_get_user_conversations_simple(user_id: str):
    """直接从Redis获取用户对话列表"""
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = max(1, min(limit, 50))
        
        logger.info(f"📋 获取用户 {user_id} 的对话列表（直接Redis方式）")
        
        # 使用简单Redis查询
        conversations = get_user_conversations_simple_sync(user_id, limit)
        
        return jsonify(success_response(
            response_text="获取用户对话列表成功",
            data={
                "user_id": user_id,
                "conversations": conversations,
                "total_count": len(conversations),
                "limit": limit
            }
        )), 200
        
    except Exception as e:
        logger.error(f"❌ 获取用户对话列表失败: {e}")
        return jsonify(internal_error_response(
            response_text=f"获取用户对话列表失败: {str(e)}"
        )), 500

@app.route('/api/v0/react/direct/conversations/<thread_id>', methods=['GET'])
def get_conversation_detail_api(thread_id: str):
    """
    获取特定对话的详细信息 - 支持include_tools开关参数（从 custom_react_agent 迁移）
    
    Query Parameters:
        - include_tools: bool, 是否包含工具调用信息，默认false
                        true: 返回完整对话（human/ai/tool/system）
                        false: 只返回human/ai消息，清理工具调用信息
        - user_id: str, 可选的用户ID验证
        
    Examples:
        GET /api/conversations/wang:20250709195048728?include_tools=true   # 完整模式
        GET /api/conversations/wang:20250709195048728?include_tools=false  # 简化模式（默认）
        GET /api/conversations/wang:20250709195048728                      # 简化模式（默认）
    """
    try:
        # 获取查询参数
        include_tools = request.args.get('include_tools', 'false').lower() == 'true'
        user_id = request.args.get('user_id')
        
        # 验证thread_id格式
        if ':' not in thread_id:
            return jsonify({
                "success": False,
                "error": "Invalid thread_id format. Expected format: user_id:timestamp",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        # 如果提供了user_id，验证thread_id是否属于该用户
        thread_user_id = thread_id.split(':')[0]
        if user_id and thread_user_id != user_id:
            return jsonify(bad_request_response(
                response_text=f"Thread ID {thread_id} does not belong to user {user_id}"
            )), 400
        
        logger.info(f"📖 获取对话详情 - Thread: {thread_id}, Include Tools: {include_tools}")
        
        # 检查enhanced_redis_api是否可用
        if get_conversation_detail_from_redis is None:
            return jsonify(service_unavailable_response(
                response_text="enhanced_redis_api 模块不可用"
            )), 503
        
        # 从Redis获取对话详情（使用我们的新函数）
        result = get_conversation_detail_from_redis(thread_id, include_tools)
        
        if not result['success']:
            logger.warning(f"⚠️ 获取对话详情失败: {result['error']}")
            return jsonify(internal_error_response(
                response_text=result['error']
            )), 404
        
        # 添加API元数据
        result['data']['api_metadata'] = {
            "timestamp": datetime.now().isoformat(),
            "api_version": "v1",
            "endpoint": "get_conversation_detail",
            "query_params": {
                "include_tools": include_tools,
                "user_id": user_id
            }
        }
        
        mode_desc = "完整模式" if include_tools else "简化模式"
        logger.info(f"✅ 成功获取对话详情 - Messages: {result['data']['message_count']}, Mode: {mode_desc}")
        
        return jsonify(success_response(
            response_text=f"获取对话详情成功 ({mode_desc})",
            data=result['data']
        )), 200
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 获取对话详情异常: {e}")
        logger.error(f"❌ 详细错误信息: {traceback.format_exc()}")
        
        return jsonify(internal_error_response(
            response_text=f"获取对话详情失败: {str(e)}"
        )), 500

@app.route('/api/v0/react/direct/conversations/<thread_id>/compare', methods=['GET'])
def compare_conversation_modes_api(thread_id: str):
    """
    比较完整模式和简化模式的对话内容
    用于调试和理解两种模式的差异（从 custom_react_agent 迁移）
    
    Examples:
        GET /api/conversations/wang:20250709195048728/compare
    """
    try:
        logger.info(f"🔍 比较对话模式 - Thread: {thread_id}")
        
        # 检查enhanced_redis_api是否可用
        if get_conversation_detail_from_redis is None:
            return jsonify({
                "success": False,
                "error": "enhanced_redis_api 模块不可用",
                "timestamp": datetime.now().isoformat()
            }), 503
        
        # 获取完整模式
        full_result = get_conversation_detail_from_redis(thread_id, include_tools=True)
        
        # 获取简化模式
        simple_result = get_conversation_detail_from_redis(thread_id, include_tools=False)
        
        if not (full_result['success'] and simple_result['success']):
            return jsonify({
                "success": False,
                "error": "无法获取对话数据进行比较",
                "timestamp": datetime.now().isoformat()
            }), 404
        
        # 构建比较结果
        comparison = {
            "thread_id": thread_id,
            "full_mode": {
                "message_count": full_result['data']['message_count'],
                "stats": full_result['data']['stats'],
                "sample_messages": full_result['data']['messages'][:3]  # 只显示前3条作为示例
            },
            "simple_mode": {
                "message_count": simple_result['data']['message_count'],
                "stats": simple_result['data']['stats'],
                "sample_messages": simple_result['data']['messages'][:3]  # 只显示前3条作为示例
            },
            "comparison_summary": {
                "message_count_difference": full_result['data']['message_count'] - simple_result['data']['message_count'],
                "tools_filtered_out": full_result['data']['stats'].get('tool_messages', 0),
                "ai_messages_with_tools": full_result['data']['stats'].get('messages_with_tools', 0),
                "filtering_effectiveness": "有效" if (full_result['data']['message_count'] - simple_result['data']['message_count']) > 0 else "无差异"
            },
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "note": "sample_messages 只显示前3条消息作为示例，完整消息请使用相应的详情API"
            }
        }
        
        logger.info(f"✅ 模式比较完成 - 完整: {comparison['full_mode']['message_count']}, 简化: {comparison['simple_mode']['message_count']}")
        
        return jsonify({
            "success": True,
            "data": comparison,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 对话模式比较失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/v0/react/direct/conversations/<thread_id>/summary', methods=['GET'])
def get_conversation_summary_api(thread_id: str):
    """
    获取对话摘要信息（只包含基本统计，不返回具体消息）（从 custom_react_agent 迁移）
    
    Query Parameters:
        - include_tools: bool, 影响统计信息的计算方式
        
    Examples:
        GET /api/conversations/wang:20250709195048728/summary?include_tools=true
    """
    try:
        include_tools = request.args.get('include_tools', 'false').lower() == 'true'
        
        # 验证thread_id格式
        if ':' not in thread_id:
            return jsonify(bad_request_response(
                response_text="Invalid thread_id format. Expected format: user_id:timestamp"
            )), 400
        
        logger.info(f"📊 获取对话摘要 - Thread: {thread_id}, Include Tools: {include_tools}")
        
        # 检查enhanced_redis_api是否可用
        if get_conversation_detail_from_redis is None:
            return jsonify(service_unavailable_response(
                response_text="enhanced_redis_api 模块不可用"
            )), 503
        
        # 获取完整对话信息
        result = get_conversation_detail_from_redis(thread_id, include_tools)
        
        if not result['success']:
            return jsonify(internal_error_response(
                response_text=result['error']
            )), 404
        
        # 只返回摘要信息，不包含具体消息
        data = result['data']
        summary = {
            "thread_id": data['thread_id'],
            "user_id": data['user_id'],
            "include_tools": data['include_tools'],
            "message_count": data['message_count'],
            "stats": data['stats'],
            "metadata": data['metadata'],
            "first_message_preview": None,
            "last_message_preview": None,
            "conversation_preview": None
        }
        
        # 添加消息预览
        messages = data.get('messages', [])
        if messages:
            # 第一条human消息预览
            for msg in messages:
                if msg['role'] == 'human':
                    content = str(msg['content'])
                    summary['first_message_preview'] = content[:100] + "..." if len(content) > 100 else content
                    break
            
            # 最后一条ai消息预览
            for msg in reversed(messages):
                if msg['role'] == 'ai' and msg.get('content', '').strip():
                    content = str(msg['content'])
                    summary['last_message_preview'] = content[:100] + "..." if len(content) > 100 else content
                    break
            
            # 生成对话预览（第一条human消息）
            summary['conversation_preview'] = summary['first_message_preview']
        
        # 添加API元数据
        summary['api_metadata'] = {
            "timestamp": datetime.now().isoformat(),
            "api_version": "v1",
            "endpoint": "get_conversation_summary"
        }
        
        logger.info(f"✅ 成功获取对话摘要")
        
        return jsonify(success_response(
            response_text="获取对话摘要成功",
            data=summary
        )), 200
        
    except Exception as e:
        logger.error(f"❌ 获取对话摘要失败: {e}")
        return jsonify(internal_error_response(
            response_text=f"获取对话摘要失败: {str(e)}"
        )), 500



# Data Pipeline 全局变量 - 从 citu_app.py 迁移
data_pipeline_manager = None
data_pipeline_file_manager = None

def get_data_pipeline_manager():
    """获取Data Pipeline管理器单例（从 citu_app.py 迁移）"""
    global data_pipeline_manager
    if data_pipeline_manager is None:
        data_pipeline_manager = SimpleWorkflowManager()
    return data_pipeline_manager

def get_data_pipeline_file_manager():
    """获取Data Pipeline文件管理器单例（从 citu_app.py 迁移）"""
    global data_pipeline_file_manager
    if data_pipeline_file_manager is None:
        data_pipeline_file_manager = SimpleFileManager()
    return data_pipeline_file_manager

# ==================== QA缓存管理API (从 citu_app.py 迁移) ====================

@app.route('/api/v0/qa_cache_stats', methods=['GET'])
def qa_cache_stats():
    """获取问答缓存统计信息（从 citu_app.py 迁移）"""
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

@app.route('/api/v0/qa_cache_cleanup', methods=['POST'])
def qa_cache_cleanup():
    """清空所有问答缓存（从 citu_app.py 迁移）"""
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

# ==================== Database API (从 citu_app.py 迁移) ====================

@app.route('/api/v0/database/tables', methods=['POST'])
def get_database_tables():
    """
    获取数据库表列表（从 citu_app.py 迁移）
    
    请求体:
    {
        "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",  // 可选，不传则使用默认配置
        "schema": "public,ods",  // 可选，支持多个schema用逗号分隔，默认为public
        "table_name_pattern": "ods_*"  // 可选，表名模式匹配，支持通配符：ods_*、*_dim、*fact*、ods_%
    }
    
    响应:
    {
        "success": true,
        "code": 200,
        "message": "获取表列表成功",
        "data": {
            "tables": ["public.table1", "public.table2", "ods.table3"],
            "total": 3,
            "schemas": ["public", "ods"],
            "table_name_pattern": "ods_*"
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
        table_name_pattern = req.get('table_name_pattern')
        
        # 创建表检查API实例
        table_inspector = TableInspectorAPI()
        
        # 使用asyncio运行异步方法
        async def get_tables():
            return await table_inspector.get_tables_list(db_connection, schema, table_name_pattern)
        
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
        
        # 如果使用了表名模式，添加到响应中
        if table_name_pattern:
            response_data["table_name_pattern"] = table_name_pattern
        
        return jsonify(success_response(
            response_text="获取表列表成功",
            data=response_data
        )), 200
        
    except Exception as e:
        logger.error(f"获取数据库表列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text=f"获取表列表失败: {str(e)}"
        )), 500

@app.route('/api/v0/database/table/ddl', methods=['POST'])
def get_table_ddl():
    """
    获取表的DDL语句或MD文档（从 citu_app.py 迁移）
    
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

# ==================== Data Pipeline API (从 citu_app.py 迁移) ====================

@app.route('/api/v0/data_pipeline/tasks', methods=['POST'])
def create_data_pipeline_task():
    """创建数据管道任务（从 citu_app.py 迁移）"""
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/execute', methods=['POST'])
def execute_data_pipeline_task(task_id):
    """执行数据管道任务（从 citu_app.py 迁移）"""
    try:
        req = request.get_json(force=True) if request.is_json else {}
        execution_mode = req.get('execution_mode', 'complete')
        step_name = req.get('step_name')
        
        # 新增：Vector表管理参数
        backup_vector_tables = req.get('backup_vector_tables', False)
        truncate_vector_tables = req.get('truncate_vector_tables', False)
        skip_training = req.get('skip_training', False)
        
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
        
        # 新增：Vector表管理参数验证和警告
        if execution_mode == 'step' and step_name != 'training_load':
            if backup_vector_tables or truncate_vector_tables or skip_training:
                logger.warning(
                    f"⚠️ Vector表管理参数仅在training_load步骤有效，当前步骤: {step_name}，忽略参数"
                )
                backup_vector_tables = False
                truncate_vector_tables = False
                skip_training = False
        
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
                    
                # 新增：Vector表管理参数传递
                if backup_vector_tables:
                    cmd.append("--backup-vector-tables")
                if truncate_vector_tables:
                    cmd.append("--truncate-vector-tables")
                if skip_training:
                    cmd.append("--skip-training")
                
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
        
        # 新增：记录Vector表管理参数到日志
        if backup_vector_tables or truncate_vector_tables:
            logger.info(f"📋 API请求包含Vector表管理参数: backup={backup_vector_tables}, truncate={truncate_vector_tables}")
        
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>', methods=['GET'])
def get_data_pipeline_task_status(task_id):
    """
    获取数据管道任务状态（从 citu_app.py 迁移）
    
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/logs', methods=['GET'])
def get_data_pipeline_task_logs(task_id):
    """
    获取数据管道任务日志（从任务目录文件读取）（从 citu_app.py 迁移）
    
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

@app.route('/api/v0/data_pipeline/tasks', methods=['GET'])
def list_data_pipeline_tasks():
    """获取数据管道任务列表（从 citu_app.py 迁移）"""
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

@app.route('/api/v0/data_pipeline/tasks/query', methods=['POST'])
def query_data_pipeline_tasks():
    """
    高级查询数据管道任务列表（从 citu_app.py 迁移）
    
    支持复杂筛选、排序、分页功能
    
    请求体:
    {
        "page": 1,                          // 页码，必须大于0，默认1
        "page_size": 20,                    // 每页大小，1-100之间，默认20
        "status": "completed",              // 可选，任务状态筛选："pending"|"running"|"completed"|"failed"|"cancelled"
        "task_name": "highway",             // 可选，任务名称模糊搜索，最大100字符
        "created_by": "user123",            // 可选，创建者精确匹配
        "db_name": "highway_db",            // 可选，数据库名称精确匹配
        "created_time_start": "2025-01-01T00:00:00",  // 可选，创建时间范围开始
        "created_time_end": "2025-12-31T23:59:59",    // 可选，创建时间范围结束
        "started_time_start": "2025-01-01T00:00:00",  // 可选，开始时间范围开始
        "started_time_end": "2025-12-31T23:59:59",    // 可选，开始时间范围结束
        "completed_time_start": "2025-01-01T00:00:00", // 可选，完成时间范围开始
        "completed_time_end": "2025-12-31T23:59:59",   // 可选，完成时间范围结束
        "sort_by": "created_at",            // 可选，排序字段："created_at"|"started_at"|"completed_at"|"task_name"|"status"，默认"created_at"
        "sort_order": "desc"                // 可选，排序方向："asc"|"desc"，默认"desc"
    }
    """
    try:
        # 获取请求数据
        req = request.get_json(force=True) if request.is_json else {}
        
        # 解析参数，设置默认值
        page = req.get('page', 1)
        page_size = req.get('page_size', 20)
        status = req.get('status')
        task_name = req.get('task_name')
        created_by = req.get('created_by')
        db_name = req.get('db_name')
        created_time_start = req.get('created_time_start')
        created_time_end = req.get('created_time_end')
        started_time_start = req.get('started_time_start')
        started_time_end = req.get('started_time_end')
        completed_time_start = req.get('completed_time_start')
        completed_time_end = req.get('completed_time_end')
        sort_by = req.get('sort_by', 'created_at')
        sort_order = req.get('sort_order', 'desc')
        
        # 参数验证
        # 验证分页参数
        if page < 1:
            return jsonify(bad_request_response(
                response_text="页码必须大于0",
                invalid_params=['page']
            )), 400
        
        if page_size < 1 or page_size > 100:
            return jsonify(bad_request_response(
                response_text="每页大小必须在1-100之间",
                invalid_params=['page_size']
            )), 400
        
        # 验证任务名称长度
        if task_name and len(task_name) > 100:
            return jsonify(bad_request_response(
                response_text="任务名称搜索关键词最大长度为100字符",
                invalid_params=['task_name']
            )), 400
        
        # 验证排序参数
        allowed_sort_fields = ['created_at', 'started_at', 'completed_at', 'task_name', 'status']
        if sort_by not in allowed_sort_fields:
            return jsonify(bad_request_response(
                response_text=f"不支持的排序字段: {sort_by}，支持的字段: {', '.join(allowed_sort_fields)}",
                invalid_params=['sort_by']
            )), 400
        
        if sort_order.lower() not in ['asc', 'desc']:
            return jsonify(bad_request_response(
                response_text="排序方向必须是 'asc' 或 'desc'",
                invalid_params=['sort_order']
            )), 400
        
        # 验证状态筛选
        if status:
            allowed_statuses = ['pending', 'running', 'completed', 'failed', 'cancelled']
            if status not in allowed_statuses:
                return jsonify(bad_request_response(
                    response_text=f"不支持的状态值: {status}，支持的状态: {', '.join(allowed_statuses)}",
                    invalid_params=['status']
                )), 400
        
        # 调用管理器执行查询
        manager = get_data_pipeline_manager()
        result = manager.query_tasks_advanced(
            page=page,
            page_size=page_size,
            status=status,
            task_name=task_name,
            created_by=created_by,
            db_name=db_name,
            created_time_start=created_time_start,
            created_time_end=created_time_end,
            started_time_start=started_time_start,
            started_time_end=started_time_end,
            completed_time_start=completed_time_start,
            completed_time_end=completed_time_end,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 格式化任务列表
        formatted_tasks = []
        for task in result['tasks']:
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
                "directory_exists": task.get('directory_exists', True),
                "updated_at": task['updated_at'].isoformat() if task.get('updated_at') else None
            })
        
        # 构建响应数据
        response_data = {
            "tasks": formatted_tasks,
            "pagination": result['pagination'],
            "filters_applied": {
                k: v for k, v in {
                    "status": status,
                    "task_name": task_name,
                    "created_by": created_by,
                    "db_name": db_name,
                    "created_time_start": created_time_start,
                    "created_time_end": created_time_end,
                    "started_time_start": started_time_start,
                    "started_time_end": started_time_end,
                    "completed_time_start": completed_time_start,
                    "completed_time_end": completed_time_end
                }.items() if v
            },
            "sort_applied": {
                "sort_by": sort_by,
                "sort_order": sort_order
            },
            "query_time": result.get('query_time', '0.000s')
        }
        
        return jsonify(success_response(
            response_text="查询任务列表成功",
            data=response_data
        ))
        
    except Exception as e:
        logger.error(f"查询数据管道任务列表失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询任务列表失败，请稍后重试"
        )), 500

@app.route('/api/v0/data_pipeline/tasks/<task_id>/files', methods=['GET'])
def get_data_pipeline_task_files(task_id):
    """获取任务文件列表（从 citu_app.py 迁移）"""
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/files/<file_name>', methods=['GET'])
def download_data_pipeline_task_file(task_id, file_name):
    """下载任务文件（从 citu_app.py 迁移）"""
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/upload-table-list', methods=['POST'])
def upload_table_list_file(task_id):
    """
    上传表清单文件（从 citu_app.py 迁移）
    
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/table-list-info', methods=['GET'])
def get_table_list_info(task_id):
    """
    获取任务的表清单文件信息（从 citu_app.py 迁移）
    
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/table-list', methods=['POST'])
def create_table_list_from_names(task_id):
    """
    通过POST方式提交表名列表并创建table_list.txt文件（从 citu_app.py 迁移）
    
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

@app.route('/api/v0/data_pipeline/tasks/<task_id>/files', methods=['POST'])
def upload_file_to_task(task_id):
    """
    上传文件到指定任务目录（从 citu_app.py 迁移）
    
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

# 任务目录删除功能（从 citu_app.py 迁移）
import shutil
from pathlib import Path
import psycopg2
from app_config import PGVECTOR_CONFIG

def delete_task_directory_simple(task_id, delete_database_records=False):
    """
    简单的任务目录删除功能（从 citu_app.py 迁移）
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
            operation_message = "目录删除成功"
        else:
            directory_deleted = False
            operation_message = "目录不存在，无需删除"
        
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
            "deleted_at": datetime.now().isoformat(),
            "operation_message": operation_message  # 新增：具体的操作消息
        }
        
    except Exception as e:
        logger.error(f"删除任务目录失败: {task_id}, 错误: {str(e)}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
            "error_code": "DELETE_FAILED",
            "operation_message": f"删除操作失败: {str(e)}"  # 新增：失败消息
        }

@app.route('/api/v0/data_pipeline/tasks', methods=['DELETE'])
def delete_tasks():
    """删除任务目录（支持单个和批量）（从 citu_app.py 迁移）"""
    try:
        # 智能获取参数：支持JSON body和URL查询参数两种方式
        def get_request_parameter(param_name, array_param_name=None):
            """从JSON body或URL查询参数中获取参数值"""
            # 1. 优先从JSON body获取
            if request.is_json:
                try:
                    json_data = request.get_json()
                    if json_data and param_name in json_data:
                        return json_data[param_name]
                except:
                    pass
            
            # 2. 从URL查询参数获取
            if param_name in request.args:
                value = request.args.get(param_name)
                # 处理布尔值
                if value.lower() in ('true', '1', 'yes'):
                    return True
                elif value.lower() in ('false', '0', 'no'):
                    return False
                return value
            
            # 3. 处理数组参数（如 task_ids[]）
            if array_param_name and array_param_name in request.args:
                return request.args.getlist(array_param_name)
            
            return None
        
        # 获取参数
        task_ids = get_request_parameter('task_ids', 'task_ids[]')
        confirm = get_request_parameter('confirm')
        
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
        delete_database_records = get_request_parameter('delete_database_records') or False
        continue_on_error = get_request_parameter('continue_on_error')
        if continue_on_error is None:
            continue_on_error = True
        
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
        
        # 构建智能响应消息
        if len(task_ids) == 1:
            # 单个删除：使用具体的操作消息
            if summary["failed"] == 0:
                # 从deleted_tasks中获取具体的操作消息
                operation_msg = deleted_tasks[0].get('operation_message', '任务处理完成')
                message = operation_msg
            else:
                # 从failed_tasks中获取错误消息
                error_msg = failed_tasks[0].get('error', '删除失败')
                message = f"任务删除失败: {error_msg}"
        else:
            # 批量删除：统计各种操作结果
            directory_deleted_count = sum(1 for task in deleted_tasks if task.get('directory_deleted', False))
            directory_not_exist_count = sum(1 for task in deleted_tasks if not task.get('directory_deleted', False))
            
            if summary["failed"] == 0:
                # 全部成功
                if directory_deleted_count > 0 and directory_not_exist_count > 0:
                    message = f"批量操作完成：{directory_deleted_count}个目录已删除，{directory_not_exist_count}个目录不存在"
                elif directory_deleted_count > 0:
                    message = f"批量删除完成：成功删除{directory_deleted_count}个目录"
                elif directory_not_exist_count > 0:
                    message = f"批量操作完成：{directory_not_exist_count}个目录不存在，无需删除"
                else:
                    message = "批量操作完成"
            elif summary["successfully_deleted"] == 0:
                message = f"批量删除失败：{summary['failed']}个任务处理失败"
            else:
                message = f"批量删除部分完成：成功{summary['successfully_deleted']}个，失败{summary['failed']}个"
        
        return jsonify(success_response(
            response_text=message,
            data=batch_result
        )), 200
        
    except Exception as e:
        logger.error(f"删除任务失败: 错误: {str(e)}")
        return jsonify(internal_error_response(
            response_text="删除任务失败，请稍后重试"
        )), 500

@app.route('/api/v0/data_pipeline/tasks/<task_id>/logs/query', methods=['POST'])
def query_data_pipeline_task_logs(task_id):
    """
    高级查询数据管道任务日志（从 citu_app.py 迁移）
    
    支持复杂筛选、排序、分页功能
    
    请求体:
    {
        "page": 1,                          // 页码，必须大于0，默认1
        "page_size": 50,                    // 每页大小，1-500之间，默认50
        "level": "ERROR",                   // 可选，日志级别筛选："DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL"
        "start_time": "2025-01-01 00:00:00", // 可选，开始时间范围 (YYYY-MM-DD HH:MM:SS)
        "end_time": "2025-01-02 23:59:59",   // 可选，结束时间范围 (YYYY-MM-DD HH:MM:SS)
        "keyword": "failed",                 // 可选，关键字搜索（消息内容模糊匹配）
        "logger_name": "DDLGenerator",       // 可选，日志记录器名称精确匹配
        "step_name": "ddl_generation",       // 可选，执行步骤名称精确匹配
        "sort_by": "timestamp",              // 可选，排序字段："timestamp"|"level"|"logger"|"step"|"line_number"，默认"timestamp"
        "sort_order": "desc"                 // 可选，排序方向："asc"|"desc"，默认"desc"
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
        
        # 解析请求数据
        request_data = request.get_json() or {}
        
        # 参数验证
        def _is_valid_time_format(time_str):
            """验证时间格式是否有效"""
            if not time_str:
                return True
            
            # 支持的时间格式
            time_formats = [
                '%Y-%m-%d %H:%M:%S',     # 2025-01-01 00:00:00
                '%Y-%m-%d',              # 2025-01-01
                '%Y-%m-%dT%H:%M:%S',     # 2025-01-01T00:00:00
                '%Y-%m-%dT%H:%M:%S.%f',  # 2025-01-01T00:00:00.123456
            ]
            
            for fmt in time_formats:
                try:
                    from datetime import datetime
                    datetime.strptime(time_str, fmt)
                    return True
                except ValueError:
                    continue
            return False
        
        # 提取和验证参数
        page = request_data.get('page', 1)
        page_size = request_data.get('page_size', 50)
        level = request_data.get('level')
        start_time = request_data.get('start_time')
        end_time = request_data.get('end_time')
        keyword = request_data.get('keyword')
        logger_name = request_data.get('logger_name')
        step_name = request_data.get('step_name')
        sort_by = request_data.get('sort_by', 'timestamp')
        sort_order = request_data.get('sort_order', 'desc')
        
        # 参数验证
        if not isinstance(page, int) or page < 1:
            return jsonify(bad_request_response(
                response_text="页码必须是大于0的整数"
            )), 400
        
        if not isinstance(page_size, int) or page_size < 1 or page_size > 500:
            return jsonify(bad_request_response(
                response_text="每页大小必须是1-500之间的整数"
            )), 400
        
        # 验证日志级别
        if level and level.upper() not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            return jsonify(bad_request_response(
                response_text="日志级别必须是DEBUG、INFO、WARNING、ERROR、CRITICAL之一"
            )), 400
        
        # 验证时间格式
        if not _is_valid_time_format(start_time):
            return jsonify(bad_request_response(
                response_text="开始时间格式无效，支持格式：YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD"
            )), 400
        
        if not _is_valid_time_format(end_time):
            return jsonify(bad_request_response(
                response_text="结束时间格式无效，支持格式：YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD"
            )), 400
        
        # 验证关键字长度
        if keyword and len(keyword) > 200:
            return jsonify(bad_request_response(
                response_text="关键字长度不能超过200个字符"
            )), 400
        
        # 验证排序字段
        allowed_sort_fields = ['timestamp', 'level', 'logger', 'step', 'line_number']
        if sort_by not in allowed_sort_fields:
            return jsonify(bad_request_response(
                response_text=f"排序字段必须是以下之一: {', '.join(allowed_sort_fields)}"
            )), 400
        
        # 验证排序方向
        if sort_order.lower() not in ['asc', 'desc']:
            return jsonify(bad_request_response(
                response_text="排序方向必须是asc或desc"
            )), 400
        
        # 创建工作流执行器并查询日志
        from data_pipeline.api.simple_workflow import SimpleWorkflowExecutor
        executor = SimpleWorkflowExecutor(task_id)
        
        try:
            result = executor.query_logs_advanced(
                page=page,
                page_size=page_size,
                level=level,
                start_time=start_time,
                end_time=end_time,
                keyword=keyword,
                logger_name=logger_name,
                step_name=step_name,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            return jsonify(success_response(
                response_text="查询任务日志成功",
                data=result
            ))
            
        finally:
            executor.cleanup()
        
    except Exception as e:
        logger.error(f"查询数据管道任务日志失败: {str(e)}")
        return jsonify(internal_error_response(
            response_text="查询任务日志失败，请稍后重试"
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
    
    try:
        # 尝试使用ASGI模式启动（推荐）
        import uvicorn
        from asgiref.wsgi import WsgiToAsgi
        
        logger.info("🚀 使用ASGI模式启动异步Flask应用...")
        logger.info("   这将解决事件循环冲突问题，支持LangGraph异步checkpoint保存")
        
        # 将Flask WSGI应用转换为ASGI应用
        asgi_app = WsgiToAsgi(app)
        
        # 使用uvicorn启动ASGI应用
        uvicorn.run(
            asgi_app,
            host="0.0.0.0",
            port=8084,
            log_level="info",
            access_log=True
        )
        
    except ImportError as e:
        # 如果缺少ASGI依赖，fallback到传统Flask模式
        logger.warning("⚠️ ASGI依赖缺失，使用传统Flask模式启动")
        logger.warning("   建议安装: pip install uvicorn asgiref")
        logger.warning("   传统模式可能存在异步事件循环冲突问题")
        
        # 启动标准Flask应用（支持异步路由）
        app.run(host="0.0.0.0", port=8084, debug=False, threaded=True)