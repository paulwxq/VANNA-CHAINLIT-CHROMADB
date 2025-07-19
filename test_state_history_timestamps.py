#!/usr/bin/env python3
"""
测试LangGraph StateSnapshot的created_at时间戳
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from react_agent.agent import CustomReactAgent

async def test_state_history_timestamps():
    """测试StateSnapshot的created_at时间戳"""
    print("=" * 60)
    print("测试LangGraph StateSnapshot的created_at时间戳")
    print("=" * 60)
    
    try:
        # 初始化Agent
        print("🚀 初始化Agent...")
        agent = await CustomReactAgent.create()
        
        thread_id = "wang10:20250717211620915"
        print(f"\n📖 分析Thread: {thread_id}")
        
        # 使用get_state_history获取所有历史状态
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        print(f"🔍 获取状态历史...")
        # agent_executor是编译后的graph
        if hasattr(agent, 'agent_executor') and hasattr(agent.agent_executor, 'get_state_history'):
            print(f"✅ 找到get_state_history方法")
            
            # 获取前5个历史状态
            history_count = 0
            for state_snapshot in agent.agent_executor.get_state_history(thread_config):
                history_count += 1
                if history_count > 5:  # 只看前5个状态
                    break
                
                print(f"\n📊 状态 #{history_count}:")
                print(f"  🆔 Checkpoint ID: {state_snapshot.config.get('configurable', {}).get('checkpoint_id', 'N/A')}")
                print(f"  ⏰ Created At: {state_snapshot.created_at}")
                print(f"  📝 Messages Count: {len(state_snapshot.values.get('messages', []))}")
                print(f"  🔄 Next: {state_snapshot.next}")
                print(f"  📋 Step: {state_snapshot.metadata.get('step', 'N/A')}")
                
                # 解析时间戳
                if state_snapshot.created_at:
                    try:
                        dt = datetime.fromisoformat(state_snapshot.created_at.replace('Z', '+00:00'))
                        print(f"  📅 解析后时间: {dt}")
                        print(f"  🕐 本地时间: {dt.astimezone()}")
                    except Exception as e:
                        print(f"  ❌ 时间解析失败: {e}")
                
                # 如果有消息，显示最后一条消息的类型
                messages = state_snapshot.values.get('messages', [])
                if messages:
                    last_msg = messages[-1]
                    msg_type = getattr(last_msg, 'type', 'unknown')
                    content_preview = str(getattr(last_msg, 'content', ''))[:50]
                    print(f"  💬 最后消息: {msg_type} - {content_preview}...")
            
            if history_count == 0:
                print("❌ 没有找到历史状态")
            else:
                print(f"\n✅ 总共分析了 {history_count} 个历史状态")
                
        else:
            print("❌ 未找到get_state_history方法")
            print("📝 可用方法:")
            if hasattr(agent, 'agent_executor'):
                methods = [m for m in dir(agent.agent_executor) if not m.startswith('_')]
                print(f"  agent_executor methods: {methods}")
            
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_current_state_timestamp():
    """测试当前状态的时间戳"""
    print(f"\n" + "=" * 60)
    print("测试当前状态的时间戳")
    print("=" * 60)
    
    try:
        # 初始化Agent
        agent = await CustomReactAgent.create()
        
        thread_id = "wang10:20250717211620915"
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        print(f"🔍 获取当前状态...")
        if hasattr(agent, 'agent_executor') and hasattr(agent.agent_executor, 'get_state'):
            current_state = agent.agent_executor.get_state(thread_config)
            
            print(f"📊 当前状态:")
            print(f"  🆔 Checkpoint ID: {current_state.config.get('configurable', {}).get('checkpoint_id', 'N/A')}")
            print(f"  ⏰ Created At: {current_state.created_at}")
            print(f"  📝 Messages Count: {len(current_state.values.get('messages', []))}")
            print(f"  🔄 Next: {current_state.next}")
            
            if current_state.created_at:
                try:
                    dt = datetime.fromisoformat(current_state.created_at.replace('Z', '+00:00'))
                    print(f"  📅 解析后时间: {dt}")
                    print(f"  🕐 本地时间: {dt.astimezone()}")
                except Exception as e:
                    print(f"  ❌ 时间解析失败: {e}")
        else:
            print("❌ 未找到get_state方法")
            
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_checkpointer_access():
    """测试直接通过checkpointer访问历史"""
    print(f"\n" + "=" * 60)
    print("测试通过checkpointer访问历史")
    print("=" * 60)
    
    try:
        # 初始化Agent
        agent = await CustomReactAgent.create()
        
        thread_id = "wang10:20250717211620915"
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        print(f"🔍 通过checkpointer获取历史...")
        if hasattr(agent, 'checkpointer') and hasattr(agent.checkpointer, 'alist'):
            print(f"✅ 找到checkpointer.alist方法")
            
            # 获取前5个checkpoint
            history_count = 0
            async for checkpoint_tuple in agent.checkpointer.alist(thread_config):
                history_count += 1
                if history_count > 5:  # 只看前5个状态
                    break
                
                print(f"\n📊 Checkpoint #{history_count}:")
                print(f"  🆔 Config: {checkpoint_tuple.config}")
                print(f"  ⏰ Checkpoint TS: {checkpoint_tuple.checkpoint.get('ts', 'N/A')}")
                print(f"  📋 Metadata: {checkpoint_tuple.metadata}")
                
                # 解析checkpoint中的时间戳
                ts_value = checkpoint_tuple.checkpoint.get('ts')
                if ts_value:
                    try:
                        dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                        print(f"  📅 解析后时间: {dt}")
                        print(f"  🕐 本地时间: {dt.astimezone()}")
                    except Exception as e:
                        print(f"  ❌ 时间解析失败: {e}")
                
                # 检查消息
                messages = checkpoint_tuple.checkpoint.get('channel_values', {}).get('messages', [])
                print(f"  📝 Messages Count: {len(messages)}")
                
            if history_count == 0:
                print("❌ 没有找到checkpoint历史")
            else:
                print(f"\n✅ 总共分析了 {history_count} 个checkpoint")
        else:
            print("❌ 未找到checkpointer.alist方法")
            
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_state_history_timestamps())
    asyncio.run(test_current_state_timestamp())
    asyncio.run(test_checkpointer_access()) 