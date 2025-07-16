"""
简单Redis查询API函数，替换复杂的LangGraph方法
"""
import redis
import json
from typing import List, Dict, Any
from datetime import datetime

def get_user_conversations_simple_sync(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    直接从Redis获取用户对话，不使用LangGraph
    同步版本，避免事件循环问题
    """
    try:
        # 创建Redis连接
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        # 测试连接
        redis_client.ping()
        
        # 扫描用户的checkpoint keys
        pattern = f"checkpoint:{user_id}:*"
        print(f"🔍 扫描模式: {pattern}")
        
        # 获取所有匹配的keys
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        print(f"📋 找到 {len(keys)} 个keys")
        
        # 解析thread信息
        thread_data = {}
        for key in keys:
            try:
                # key格式: checkpoint:user_id:timestamp:status:uuid
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
                print(f"解析key失败 {key}: {e}")
                continue
        
        print(f"📊 找到 {len(thread_data)} 个thread")
        
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
                
                # 获取该thread的最新checkpoint数据
                latest_key = None
                for key in thread_info["keys"]:
                    if latest_key is None or key > latest_key:
                        latest_key = key
                
                if latest_key:
                    # 直接从Redis获取数据
                    data = redis_client.get(latest_key)
                    if data:
                        try:
                            # 尝试解析JSON数据
                            checkpoint_data = json.loads(data)
                            
                            # 提取消息信息
                            messages = checkpoint_data.get('channel_values', {}).get('messages', [])
                            
                            # 生成对话预览
                            preview = "空对话"
                            if messages:
                                for msg in messages:
                                    # 处理不同的消息格式
                                    if isinstance(msg, dict):
                                        msg_type = msg.get('type', '')
                                        if msg_type == 'human':
                                            content = str(msg.get('content', ''))
                                            preview = content[:50] + "..." if len(content) > 50 else content
                                            break
                                    elif hasattr(msg, 'content') and hasattr(msg, '__class__'):
                                        # LangChain消息对象
                                        if msg.__class__.__name__ == 'HumanMessage':
                                            content = str(msg.content)
                                            preview = content[:50] + "..." if len(content) > 50 else content
                                            break
                            
                            conversations.append({
                                "thread_id": thread_id,
                                "user_id": user_id,
                                "timestamp": thread_info["timestamp"],
                                "message_count": len(messages),
                                "conversation_preview": preview,
                                "formatted_time": format_timestamp_simple(thread_info["timestamp"])
                            })
                            
                        except json.JSONDecodeError:
                            print(f"❌ 解析JSON失败: {latest_key}")
                            continue
                        except Exception as e:
                            print(f"❌ 处理数据失败: {e}")
                            continue
                    
            except Exception as e:
                print(f"❌ 处理thread {thread_info['thread_id']} 失败: {e}")
                continue
        
        redis_client.close()
        print(f"✅ 返回 {len(conversations)} 个对话")
        return conversations
        
    except Exception as e:
        print(f"❌ Redis查询失败: {e}")
        return []

def get_conversation_history_simple_sync(thread_id: str) -> List[Dict[str, Any]]:
    """
    直接从Redis获取对话历史，不使用LangGraph
    """
    try:
        # 创建Redis连接
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
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
            redis_client.close()
            return []
        
        # 获取最新的checkpoint
        latest_key = max(keys)
        data = redis_client.get(latest_key)
        
        if not data:
            redis_client.close()
            return []
        
        # 解析数据
        checkpoint_data = json.loads(data)
        messages = checkpoint_data.get('channel_values', {}).get('messages', [])
        
        # 转换消息格式
        history = []
        for msg in messages:
            if isinstance(msg, dict):
                # 已经是字典格式
                msg_type = msg.get('type', 'unknown')
                if msg_type == 'human':
                    role = "human"
                elif msg_type == 'tool':
                    role = "tool"
                else:
                    role = "ai"
                
                history.append({
                    "type": role,
                    "content": msg.get('content', ''),
                    "tool_calls": msg.get('tool_calls', None)
                })
            elif hasattr(msg, '__class__'):
                # LangChain消息对象
                class_name = msg.__class__.__name__
                if class_name == 'HumanMessage':
                    role = "human"
                elif class_name == 'ToolMessage':
                    role = "tool"
                else:
                    role = "ai"
                
                history.append({
                    "type": role,
                    "content": getattr(msg, 'content', ''),
                    "tool_calls": getattr(msg, 'tool_calls', None)
                })
        
        redis_client.close()
        return history
        
    except Exception as e:
        print(f"❌ 获取对话历史失败: {e}")
        return []

def format_timestamp_simple(timestamp: str) -> str:
    """格式化时间戳"""
    try:
        if len(timestamp) >= 14:
            year = timestamp[:4]
            month = timestamp[4:6]
            day = timestamp[6:8]
            hour = timestamp[8:10]
            minute = timestamp[10:12]
            second = timestamp[12:14]
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
    except Exception:
        pass
    return timestamp

# 测试函数
def test_simple_redis_functions():
    """测试简单Redis函数"""
    print("🧪 测试简单Redis函数...")
    
    try:
        # 测试获取对话列表
        print("1. 测试获取用户对话列表...")
        conversations = get_user_conversations_simple_sync("doudou", 5)
        print(f"   结果: {len(conversations)} 个对话")
        
        if conversations:
            for conv in conversations:
                print(f"   - {conv['thread_id']}: {conv['conversation_preview']}")
            
            # 测试获取对话详情
            print("2. 测试获取对话详情...")
            first_thread = conversations[0]['thread_id']
            history = get_conversation_history_simple_sync(first_thread)
            print(f"   结果: {len(history)} 条消息")
            
            for i, msg in enumerate(history[:3]):
                print(f"   [{i+1}] {msg['type']}: {str(msg['content'])[:50]}...")
        
        print("✅ 测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_simple_redis_functions() 