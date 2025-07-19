#!/usr/bin/env python3
"""
测试conversation_state['ts']的确切含义
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from react_agent.agent import CustomReactAgent

async def test_ts_meaning():
    """测试ts字段的含义"""
    print("=" * 60)
    print("测试conversation_state['ts']的含义")
    print("=" * 60)
    
    try:
        # 初始化Agent
        print("🚀 初始化Agent...")
        agent = await CustomReactAgent.create()
        
        # 测试多个不同的thread_id
        thread_ids = [
            "wang10:20250717211620915",  # 原始的长对话
            # 如果有其他thread_id可以添加
        ]
        
        for thread_id in thread_ids:
            print(f"\n📖 分析Thread: {thread_id}")
            
            # 从checkpointer获取原始数据
            thread_config = {"configurable": {"thread_id": thread_id}}
            conversation_state = await agent.checkpointer.aget(thread_config)
            
            if not conversation_state:
                print(f"  ❌ 未找到对话数据")
                continue
            
            # 分析时间戳
            ts_value = conversation_state.get('ts')
            messages = conversation_state.get('channel_values', {}).get('messages', [])
            
            print(f"  📊 消息总数: {len(messages)}")
            print(f"  ⏰ conversation_state['ts']: {ts_value}")
            
            # 解析时间戳
            if ts_value:
                try:
                    dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                    print(f"  ⏰ 解析后的时间: {dt}")
                except:
                    print(f"  ❌ 时间戳解析失败")
            
            # 分析Thread ID中的时间
            if ':' in thread_id:
                parts = thread_id.split(':')
                if len(parts) >= 2:
                    timestamp_part = parts[1]
                    if len(timestamp_part) >= 14:
                        try:
                            year = timestamp_part[:4]
                            month = timestamp_part[4:6] 
                            day = timestamp_part[6:8]
                            hour = timestamp_part[8:10]
                            minute = timestamp_part[10:12]
                            second = timestamp_part[12:14]
                            ms = timestamp_part[14:] if len(timestamp_part) > 14 else "000"
                            
                            thread_dt = datetime.strptime(f"{year}-{month}-{day} {hour}:{minute}:{second}", "%Y-%m-%d %H:%M:%S")
                            print(f"  🆔 Thread ID时间: {thread_dt}")
                            
                            # 比较两个时间
                            if ts_value:
                                ts_dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00')).replace(tzinfo=None)
                                time_diff = (ts_dt - thread_dt).total_seconds()
                                print(f"  🔄 时间差: {time_diff:.2f} 秒 (ts - thread_time)")
                                
                                if abs(time_diff) < 60:
                                    print(f"    💡 时间差很小，ts可能是对话开始时间")
                                else:
                                    print(f"    💡 时间差较大，ts可能是最后更新时间")
                        except Exception as e:
                            print(f"  ❌ Thread ID时间解析失败: {e}")
            
            # 检查其他可能的时间字段
            print(f"  🔍 conversation_state所有字段:")
            for key, value in conversation_state.items():
                if 'time' in key.lower() or 'date' in key.lower() or 'created' in key.lower() or 'updated' in key.lower():
                    print(f"    {key}: {value}")
        
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def create_test_conversation():
    """创建一个测试对话来观察ts的变化"""
    print(f"\n" + "=" * 60)
    print("创建测试对话观察ts变化")
    print("=" * 60)
    
    try:
        # 初始化Agent
        agent = await CustomReactAgent.create()
        
        # 创建新的测试对话
        test_user = "test_user"
        test_message = "你好，这是一个测试消息"
        
        print(f"🚀 发送测试消息...")
        result = await agent.chat(test_message, test_user)
        
        if result.get('success'):
            thread_id = result.get('thread_id')
            print(f"✅ 对话创建成功，Thread ID: {thread_id}")
            
            # 立即检查ts
            thread_config = {"configurable": {"thread_id": thread_id}}
            conversation_state = await agent.checkpointer.aget(thread_config)
            
            if conversation_state:
                ts_value = conversation_state.get('ts')
                messages = conversation_state.get('channel_values', {}).get('messages', [])
                
                print(f"📊 首次对话后:")
                print(f"  消息数量: {len(messages)}")
                print(f"  ts值: {ts_value}")
                
                # 发送第二条消息
                print(f"\n🚀 发送第二条消息...")
                result2 = await agent.chat("这是第二条消息", test_user, thread_id)
                
                if result2.get('success'):
                    # 再次检查ts
                    conversation_state2 = await agent.checkpointer.aget(thread_config)
                    
                    if conversation_state2:
                        ts_value2 = conversation_state2.get('ts')
                        messages2 = conversation_state2.get('channel_values', {}).get('messages', [])
                        
                        print(f"📊 第二次对话后:")
                        print(f"  消息数量: {len(messages2)}")
                        print(f"  ts值: {ts_value2}")
                        
                        # 比较两次的ts
                        if ts_value != ts_value2:
                            print(f"  💡 ts值发生了变化！这说明ts是最后更新时间")
                        else:
                            print(f"  💡 ts值没有变化，可能是创建时间")
        
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试对话创建失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_ts_meaning())
    # 注释掉测试对话创建，避免产生过多测试数据
    # asyncio.run(create_test_conversation()) 