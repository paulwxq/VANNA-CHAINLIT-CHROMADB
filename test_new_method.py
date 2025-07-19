#!/usr/bin/env python3
"""
直接测试新的get_conversation_history方法
"""
import asyncio
import sys
import json
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from react_agent.agent import CustomReactAgent

async def test_new_method():
    """测试新的get_conversation_history方法"""
    print("=" * 60)
    print("直接测试新的get_conversation_history方法")
    print("=" * 60)
    
    try:
        # 初始化Agent
        print("🚀 初始化Agent...")
        agent = await CustomReactAgent.create()
        
        thread_id = "wang10:20250717211620915"
        print(f"\n📖 测试Thread: {thread_id}")
        
        # 测试不包含工具消息
        print(f"\n🔍 测试不包含工具消息...")
        result = await agent.get_conversation_history(thread_id, include_tools=False)
        
        print(f"📊 结果类型: {type(result)}")
        print(f"📝 结果键: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        if isinstance(result, dict):
            messages = result.get("messages", [])
            print(f"💬 消息数量: {len(messages)}")
            print(f"🕐 线程创建时间: {result.get('thread_created_at')}")
            print(f"📋 总checkpoint数: {result.get('total_checkpoints')}")
            
            if messages:
                print(f"\n📋 前3条消息:")
                for i, msg in enumerate(messages[:3]):
                    print(f"  消息 {i+1}:")
                    print(f"    id: {msg.get('id')}")
                    print(f"    type: {msg.get('type')}")
                    print(f"    timestamp: {msg.get('timestamp')}")
                    print(f"    content: {str(msg.get('content', ''))[:50]}...")
            
            # 保存结果
            with open('direct_method_test_no_tools.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存到 direct_method_test_no_tools.json")
        
        # 测试包含工具消息
        print(f"\n🔍 测试包含工具消息...")
        result_with_tools = await agent.get_conversation_history(thread_id, include_tools=True)
        
        if isinstance(result_with_tools, dict):
            messages_with_tools = result_with_tools.get("messages", [])
            print(f"💬 包含工具的消息数量: {len(messages_with_tools)}")
            
            # 统计消息类型
            type_counts = {}
            for msg in messages_with_tools:
                msg_type = msg.get('type', 'unknown')
                type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
            
            print(f"📊 消息类型统计:")
            for msg_type, count in type_counts.items():
                print(f"  {msg_type}: {count}")
            
            # 保存结果
            with open('direct_method_test_with_tools.json', 'w', encoding='utf-8') as f:
                json.dump(result_with_tools, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存到 direct_method_test_with_tools.json")
        
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_new_method()) 