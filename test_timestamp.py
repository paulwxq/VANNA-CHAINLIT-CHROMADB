#!/usr/bin/env python3
"""
检查conversation_state中的时间戳信息
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from react_agent.agent import CustomReactAgent

async def test_timestamp_info():
    """检查时间戳相关信息"""
    print("=" * 60)
    print("检查时间戳信息")
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
        
        # 检查conversation_state的时间戳信息
        print(f"\n🔍 conversation_state详细信息:")
        for key, value in conversation_state.items():
            print(f"  {key}: {value} (类型: {type(value).__name__})")
        
        # 特别关注ts字段
        if 'ts' in conversation_state:
            ts_value = conversation_state['ts']
            print(f"\n⏰ 时间戳分析:")
            print(f"  原始ts值: {ts_value}")
            print(f"  ts类型: {type(ts_value).__name__}")
            
            # 尝试解析时间戳
            if isinstance(ts_value, (int, float)):
                # 可能是Unix时间戳
                try:
                    if ts_value > 1000000000000:  # 毫秒时间戳
                        dt = datetime.fromtimestamp(ts_value / 1000)
                        print(f"  解析为毫秒时间戳: {dt}")
                    else:  # 秒时间戳
                        dt = datetime.fromtimestamp(ts_value)
                        print(f"  解析为秒时间戳: {dt}")
                except:
                    print(f"  时间戳解析失败")
            elif isinstance(ts_value, str):
                # 可能是ISO格式字符串
                try:
                    dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                    print(f"  解析为ISO时间: {dt}")
                except:
                    print(f"  字符串时间戳解析失败")
        
        # 检查thread_id中的时间信息
        print(f"\n🔍 Thread ID时间分析:")
        print(f"  Thread ID: {thread_id}")
        if ':' in thread_id:
            parts = thread_id.split(':')
            if len(parts) >= 2:
                timestamp_part = parts[1]  # wang10:20250717211620915
                print(f"  时间戳部分: {timestamp_part}")
                
                # 尝试解析thread_id中的时间戳
                if len(timestamp_part) >= 14:
                    try:
                        year = timestamp_part[:4]
                        month = timestamp_part[4:6] 
                        day = timestamp_part[6:8]
                        hour = timestamp_part[8:10]
                        minute = timestamp_part[10:12]
                        second = timestamp_part[12:14]
                        ms = timestamp_part[14:] if len(timestamp_part) > 14 else "000"
                        
                        dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second}.{ms}"
                        print(f"  解析为: {dt_str}")
                        
                        # 创建datetime对象
                        dt = datetime.strptime(f"{year}-{month}-{day} {hour}:{minute}:{second}", "%Y-%m-%d %H:%M:%S")
                        print(f"  DateTime对象: {dt}")
                        
                    except Exception as e:
                        print(f"  Thread ID时间解析失败: {e}")
        
        await agent.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_timestamp_info()) 