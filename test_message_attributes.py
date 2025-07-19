#!/usr/bin/env python3
"""
测试LangChain消息对象的属性，查看是否包含id和时间戳信息
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from react_agent.agent import CustomReactAgent

async def test_message_attributes():
    """测试消息对象的属性"""
    print("=" * 60)
    print("测试LangChain消息对象属性")
    print("=" * 60)
    
    try:
        # 初始化Agent
        print("🚀 初始化Agent...")
        agent = await CustomReactAgent.create()
        
        # 获取对话历史
        thread_id = "wang10:20250717211620915"
        print(f"📖 获取对话历史: {thread_id}")
        
        # 直接从checkpointer获取原始数据
        thread_config = {"configurable": {"thread_id": thread_id}}
        conversation_state = await agent.checkpointer.aget(thread_config)
        
        if not conversation_state:
            print("❌ 未找到对话数据")
            return
        
        messages = conversation_state.get('channel_values', {}).get('messages', [])
        print(f"📊 找到 {len(messages)} 条原始消息")
        
        # 分析前5条消息的属性
        print(f"\n🔍 分析前5条消息的所有属性:")
        for i, msg in enumerate(messages[:5]):
            print(f"\n消息 {i+1}:")
            print(f"  类型: {type(msg).__name__}")
            print(f"  内容长度: {len(str(msg.content))}")
            
            # 获取所有属性
            all_attrs = dir(msg)
            # 过滤出非私有属性
            public_attrs = [attr for attr in all_attrs if not attr.startswith('_')]
            print(f"  公共属性: {public_attrs}")
            
            # 检查关键属性
            key_attrs = ['id', 'timestamp', 'created_at', 'time', 'date', 'additional_kwargs', 'response_metadata']
            for attr in key_attrs:
                if hasattr(msg, attr):
                    value = getattr(msg, attr)
                    print(f"  {attr}: {value} (类型: {type(value).__name__})")
            
            # 检查additional_kwargs和response_metadata
            if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs:
                print(f"  additional_kwargs内容: {msg.additional_kwargs}")
            
            if hasattr(msg, 'response_metadata') and msg.response_metadata:
                print(f"  response_metadata内容: {msg.response_metadata}")
            
            # 打印消息的dict表示（如果有的话）
            if hasattr(msg, 'dict'):
                try:
                    msg_dict = msg.dict()
                    print(f"  dict()方法返回的键: {list(msg_dict.keys())}")
                except:
                    pass
        
        # 检查conversation_state的其他信息
        print(f"\n🔍 conversation_state的顶级键: {list(conversation_state.keys())}")
        
        # 检查是否有时间戳相关的元数据
        for key, value in conversation_state.items():
            if 'time' in key.lower() or 'date' in key.lower() or 'created' in key.lower():
                print(f"  时间相关字段 {key}: {value}")
        
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_create_new_message():
    """测试创建新消息时是否自动添加时间戳"""
    print(f"\n" + "=" * 60)
    print("测试新建消息的属性")
    print("=" * 60)
    
    try:
        from langchain_core.messages import HumanMessage, AIMessage
        from datetime import datetime
        import uuid
        
        # 创建新消息
        human_msg = HumanMessage(content="测试消息", id=str(uuid.uuid4()))
        ai_msg = AIMessage(content="AI回复", id=str(uuid.uuid4()))
        
        print("🔍 新建HumanMessage属性:")
        print(f"  id: {getattr(human_msg, 'id', 'None')}")
        print(f"  所有属性: {[attr for attr in dir(human_msg) if not attr.startswith('_')]}")
        
        print("🔍 新建AIMessage属性:")
        print(f"  id: {getattr(ai_msg, 'id', 'None')}")
        print(f"  所有属性: {[attr for attr in dir(ai_msg) if not attr.startswith('_')]}")
        
    except Exception as e:
        print(f"❌ 新消息测试失败: {e}")

if __name__ == "__main__":
    print(f"🚀 开始消息属性测试 - {asyncio.get_event_loop()}")
    asyncio.run(test_message_attributes())
    asyncio.run(test_create_new_message()) 