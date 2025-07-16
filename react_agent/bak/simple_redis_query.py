#!/usr/bin/env python3
"""
简单的Redis查询脚本，绕过LangGraph的复杂异步机制
"""
import asyncio
import redis
import json
from typing import List, Dict, Any

async def get_user_conversations_simple(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    直接从Redis获取用户对话，不使用LangGraph
    """
    # 创建Redis连接
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    try:
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
                                    if isinstance(msg, dict) and msg.get('type') == 'human':
                                        content = str(msg.get('content', ''))
                                        preview = content[:50] + "..." if len(content) > 50 else content
                                        break
                            
                            conversations.append({
                                "thread_id": thread_id,
                                "user_id": user_id,
                                "timestamp": thread_info["timestamp"],
                                "message_count": len(messages),
                                "conversation_preview": preview,
                                "formatted_time": format_timestamp(thread_info["timestamp"])
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
        
        print(f"✅ 返回 {len(conversations)} 个对话")
        return conversations
        
    finally:
        redis_client.close()

def format_timestamp(timestamp: str) -> str:
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

async def test_simple_query():
    """测试简单查询"""
    print("🧪 测试简单Redis查询...")
    
    try:
        conversations = await get_user_conversations_simple("doudou", 10)
        print(f"📋 查询结果: {len(conversations)} 个对话")
        
        for conv in conversations:
            print(f"  - {conv['thread_id']}: {conv['conversation_preview']}")
            
        return conversations
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    asyncio.run(test_simple_query()) 