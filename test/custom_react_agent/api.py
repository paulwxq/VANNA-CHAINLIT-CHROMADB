"""
Custom React Agent API 服务
提供RESTful接口用于智能问答
"""
import asyncio
import logging
import atexit
import os
from datetime import datetime
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify

try:
    # 尝试相对导入（当作为模块导入时）
    from .agent import CustomReactAgent
except ImportError:
    # 如果相对导入失败，尝试绝对导入（直接运行时）
    from agent import CustomReactAgent

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局Agent实例
_agent_instance: Optional[CustomReactAgent] = None

def validate_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证请求数据"""
    errors = []
    
    # 验证 question
    question = data.get('question', '')
    if not question or not question.strip():
        errors.append('问题不能为空')
    elif len(question) > 2000:
        errors.append('问题长度不能超过2000字符')
    
    # 验证 user_id
    user_id = data.get('user_id', 'guest')
    if user_id and len(user_id) > 50:
        errors.append('用户ID长度不能超过50字符')
    
    if errors:
        raise ValueError('; '.join(errors))
    
    return {
        'question': question.strip(),
        'user_id': user_id or 'guest',
        'thread_id': data.get('thread_id')
    }

async def initialize_agent():
    """初始化Agent"""
    global _agent_instance
    
    if _agent_instance is None:
        logger.info("🚀 正在初始化 Custom React Agent...")
        try:
            # 设置环境变量（checkpointer内部需要）
            os.environ['REDIS_URL'] = 'redis://localhost:6379'
            
            _agent_instance = await CustomReactAgent.create()
            logger.info("✅ Agent 初始化完成")
        except Exception as e:
            logger.error(f"❌ Agent 初始化失败: {e}")
            raise

async def ensure_agent_ready():
    """确保Agent实例可用"""
    global _agent_instance
    
    if _agent_instance is None:
        await initialize_agent()
    
    # 测试Agent是否还可用
    try:
        # 简单测试 - 尝试获取一个不存在用户的对话（应该返回空列表）
        test_result = await _agent_instance.get_user_recent_conversations("__test__", 1)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Agent实例不可用: {e}")
        # 重新创建Agent实例
        _agent_instance = None
        await initialize_agent()
        return True

def run_async_safely(async_func, *args, **kwargs):
    """安全地运行异步函数，处理事件循环问题"""
    try:
        # 检查是否已有事件循环
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环在运行，创建新的事件循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(async_func(*args, **kwargs))
            finally:
                new_loop.close()
        else:
            # 如果事件循环没有运行，直接使用
            return loop.run_until_complete(async_func(*args, **kwargs))
    except RuntimeError:
        # 如果没有事件循环，创建新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_func(*args, **kwargs))
        finally:
            loop.close()

def ensure_agent_ready_sync():
    """同步版本的ensure_agent_ready，用于Flask路由"""
    global _agent_instance
    
    if _agent_instance is None:
        try:
            # 使用新的事件循环初始化
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(initialize_agent())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"初始化Agent失败: {e}")
            return False
    
    return _agent_instance is not None

async def cleanup_agent():
    """清理Agent资源"""
    global _agent_instance
    
    if _agent_instance:
        await _agent_instance.close()
        logger.info("✅ Agent 资源已清理")
        _agent_instance = None

# 创建Flask应用
app = Flask(__name__)

# 注册清理函数
def cleanup_on_exit():
    """程序退出时的清理函数"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(cleanup_agent())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"清理资源时发生错误: {e}")

atexit.register(cleanup_on_exit)

@app.route("/")
def root():
    """健康检查端点"""
    return jsonify({"message": "Custom React Agent API 服务正在运行"})

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    try:
        health_status = {
            "status": "healthy",
            "agent_initialized": _agent_instance is not None,
            "timestamp": datetime.now().isoformat()
        }
        return jsonify(health_status), 200
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """智能问答接口"""
    global _agent_instance
    
    # 确保Agent已初始化
    if not _agent_instance:
        try:
            # 尝试初始化Agent（使用新的事件循环）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(initialize_agent())
            finally:
                loop.close()
        except Exception as e:
            return jsonify({
                "code": 503,
                "message": "服务未就绪",
                "success": False,
                "error": "Agent 初始化失败"
            }), 503
    
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                "code": 400,
                "message": "请求参数错误",
                "success": False,
                "error": "请求体不能为空"
            }), 400
        
        # 验证请求数据
        validated_data = validate_request_data(data)
        
        logger.info(f"📨 收到请求 - User: {validated_data['user_id']}, Question: {validated_data['question'][:50]}...")
        
        # 调用Agent处理（使用新的事件循环）
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            agent_result = loop.run_until_complete(_agent_instance.chat(
                message=validated_data['question'],
                user_id=validated_data['user_id'],
                thread_id=validated_data['thread_id']
            ))
        finally:
            loop.close()
        
        if not agent_result.get("success", False):
            # Agent处理失败
            error_msg = agent_result.get("error", "Agent处理失败")
            logger.error(f"❌ Agent处理失败: {error_msg}")
            
            return jsonify({
                "code": 500,
                "message": "处理失败",
                "success": False,
                "error": error_msg,
                "data": {
                    "react_agent_meta": {
                        "thread_id": agent_result.get("thread_id"),
                        "agent_version": "custom_react_v1",
                        "execution_path": ["error"]
                    },
                    "timestamp": datetime.now().isoformat()
                }
            }), 500
        
        # Agent处理成功，提取数据
        api_data = agent_result.get("api_data", {})
        
        # 构建最终响应
        response_data = {
            **api_data,  # 包含Agent格式化的所有数据
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ 请求处理成功 - Thread: {api_data.get('react_agent_meta', {}).get('thread_id')}")
        
        return jsonify({
            "code": 200,
            "message": "操作成功",
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        # 参数验证错误
        logger.warning(f"⚠️ 参数验证失败: {e}")
        return jsonify({
            "code": 400,
            "message": "请求参数错误",
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        # 其他未预期的错误
        logger.error(f"❌ 未预期的错误: {e}", exc_info=True)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误", 
            "success": False,
            "error": "系统异常，请稍后重试"
        }), 500

@app.route('/api/v0/react/users/<user_id>/conversations', methods=['GET'])
def get_user_conversations(user_id: str):
    """获取用户的聊天记录列表"""
    global _agent_instance
    
    try:
        # 获取查询参数
        limit = request.args.get('limit', 10, type=int)
        
        # 限制limit的范围
        limit = max(1, min(limit, 50))  # 限制在1-50之间
        
        logger.info(f"📋 获取用户 {user_id} 的对话列表，限制 {limit} 条")
        
        # 确保Agent可用
        if not ensure_agent_ready_sync():
            return jsonify({
                "success": False,
                "error": "Agent 未就绪",
                "timestamp": datetime.now().isoformat()
            }), 503
        
        # 获取对话列表
        conversations = run_async_safely(_agent_instance.get_user_recent_conversations, user_id, limit)
        
        return jsonify({
            "success": True,
            "data": {
                "user_id": user_id,
                "conversations": conversations,
                "total_count": len(conversations),
                "limit": limit
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 获取用户 {user_id} 对话列表失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/v0/react/users/<user_id>/conversations/<thread_id>', methods=['GET'])
def get_user_conversation_detail(user_id: str, thread_id: str):
    """获取特定对话的详细历史"""
    global _agent_instance
    
    try:
        # 验证thread_id格式是否匹配user_id
        if not thread_id.startswith(f"{user_id}:"):
            return jsonify({
                "success": False,
                "error": f"Thread ID {thread_id} 不属于用户 {user_id}",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        logger.info(f"📖 获取用户 {user_id} 的对话 {thread_id} 详情")
        
        # 确保Agent可用
        if not ensure_agent_ready_sync():
            return jsonify({
                "success": False,
                "error": "Agent 未就绪",
                "timestamp": datetime.now().isoformat()
            }), 503
        
        # 获取对话历史
        history = run_async_safely(_agent_instance.get_conversation_history, thread_id)
        logger.info(f"✅ 成功获取对话历史，消息数量: {len(history)}")
        
        if not history:
            return jsonify({
                "success": False,
                "error": f"未找到对话 {thread_id}",
                "timestamp": datetime.now().isoformat()
            }), 404
        
        return jsonify({
            "success": True,
            "data": {
                "user_id": user_id,
                "thread_id": thread_id,
                "message_count": len(history),
                "messages": history
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 获取对话 {thread_id} 详情失败: {e}")
        logger.error(f"❌ 详细错误信息: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# 简单Redis查询函数（测试用）
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
                        
                        conversations.append({
                            "thread_id": thread_id,
                            "user_id": user_id,
                            "timestamp": thread_info["timestamp"],
                            "message_count": len(messages),
                            "conversation_preview": preview
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

@app.route('/api/test/redis', methods=['GET'])
def test_redis_connection():
    """测试Redis连接和基本查询"""
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
    """测试简单Redis查询获取用户对话列表"""
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = max(1, min(limit, 50))
        
        logger.info(f"🧪 测试获取用户 {user_id} 的对话列表（简单Redis方式）")
        
        # 使用简单Redis查询
        conversations = get_user_conversations_simple_sync(user_id, limit)
        
        return jsonify({
            "success": True,
            "method": "simple_redis_query",
            "data": {
                "user_id": user_id,
                "conversations": conversations,
                "total_count": len(conversations),
                "limit": limit
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 测试简单Redis查询失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500
    

# 在 api.py 文件顶部的导入部分添加：
from enhanced_redis_api import get_conversation_detail_from_redis

# 在 api.py 文件中添加以下新路由：

@app.route('/api/v0/react/direct/conversations/<thread_id>', methods=['GET'])
def get_conversation_detail_api(thread_id: str):
    """
    获取特定对话的详细信息 - 支持include_tools开关参数
    
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
            return jsonify({
                "success": False,
                "error": f"Thread ID {thread_id} does not belong to user {user_id}",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        logger.info(f"📖 获取对话详情 - Thread: {thread_id}, Include Tools: {include_tools}")
        
        # 从Redis获取对话详情（使用我们的新函数）
        result = get_conversation_detail_from_redis(thread_id, include_tools)
        
        if not result['success']:
            logger.warning(f"⚠️ 获取对话详情失败: {result['error']}")
            return jsonify({
                "success": False,
                "error": result['error'],
                "timestamp": datetime.now().isoformat()
            }), 404
        
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
        
        return jsonify({
            "success": True,
            "data": result['data'],
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 获取对话详情异常: {e}")
        logger.error(f"❌ 详细错误信息: {traceback.format_exc()}")
        
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/v0/react/direct/conversations/<thread_id>/compare', methods=['GET'])
def compare_conversation_modes_api(thread_id: str):
    """
    比较完整模式和简化模式的对话内容
    用于调试和理解两种模式的差异
    
    Examples:
        GET /api/conversations/wang:20250709195048728/compare
    """
    try:
        logger.info(f"🔍 比较对话模式 - Thread: {thread_id}")
        
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
    获取对话摘要信息（只包含基本统计，不返回具体消息）
    
    Query Parameters:
        - include_tools: bool, 影响统计信息的计算方式
        
    Examples:
        GET /api/conversations/wang:20250709195048728/summary?include_tools=true
    """
    try:
        include_tools = request.args.get('include_tools', 'false').lower() == 'true'
        
        # 验证thread_id格式
        if ':' not in thread_id:
            return jsonify({
                "success": False,
                "error": "Invalid thread_id format. Expected format: user_id:timestamp",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        logger.info(f"📊 获取对话摘要 - Thread: {thread_id}, Include Tools: {include_tools}")
        
        # 获取完整对话信息
        result = get_conversation_detail_from_redis(thread_id, include_tools)
        
        if not result['success']:
            return jsonify({
                "success": False,
                "error": result['error'],
                "timestamp": datetime.now().isoformat()
            }), 404
        
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
                if msg['type'] == 'human':
                    content = str(msg['content'])
                    summary['first_message_preview'] = content[:100] + "..." if len(content) > 100 else content
                    break
            
            # 最后一条ai消息预览
            for msg in reversed(messages):
                if msg['type'] == 'ai' and msg.get('content', '').strip():
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
        
        return jsonify({
            "success": True,
            "data": summary,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 获取对话摘要失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


# 为了支持独立运行
if __name__ == "__main__":
    # 在启动前初始化Agent
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(initialize_agent())
        finally:
            loop.close()
        logger.info("✅ API 服务启动成功")
    except Exception as e:
        logger.error(f"❌ API 服务启动失败: {e}")
    
    # 启动Flask应用
    app.run(host="0.0.0.0", port=8000, debug=False) 
