#!/usr/bin/env python3
"""
测试 shell.py 新增的对话选择功能
"""
import asyncio
import sys
import os

# 确保导入路径正确
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from shell import CustomAgentShell

async def test_conversation_selection():
    """测试对话选择功能"""
    print("🧪 测试对话选择功能...")
    
    try:
        # 创建shell实例
        shell = await CustomAgentShell.create()
        print("✅ Shell创建成功!")
        
        # 设置测试数据
        shell.user_id = 'test_user'
        shell.recent_conversations = [
            {
                'thread_id': 'test_user:20250101120000001', 
                'conversation_preview': 'Python编程问题',
                'timestamp': '20250101120000001',
                'formatted_time': '2025-01-01 12:00:00'
            },
            {
                'thread_id': 'test_user:20250101130000001', 
                'conversation_preview': 'SQL查询帮助',
                'timestamp': '20250101130000001',
                'formatted_time': '2025-01-01 13:00:00'
            },
        ]
        
        print("\n📋 测试对话选择解析:")
        
        # 测试不同的选择类型
        test_cases = [
            ('1', '数字序号选择'),
            ('test_user:20250101120000001', 'Thread ID选择'),
            ('2025-01-01', '日期选择'),
            ('new', '新对话命令'),
            ('What is Python?', '新问题'),
            ('999', '无效序号'),
            ('wrong_user:20250101120000001', '无效Thread ID'),
            ('2025-12-31', '无效日期'),
        ]
        
        for user_input, description in test_cases:
            result = shell._parse_conversation_selection(user_input)
            print(f"   输入: '{user_input}' ({description})")
            print(f"   结果: {result['type']}")
            if 'message' in result:
                print(f"   消息: {result['message']}")
            elif 'thread_id' in result:
                print(f"   Thread ID: {result['thread_id']}")
            print()
        
        print("📄 测试对话列表显示:")
        shell._display_conversation_list(shell.recent_conversations)
        
        # 测试获取对话功能（这个需要真实的Agent连接）
        print("\n🔍 测试获取对话功能:")
        print("   (需要Redis和Agent连接，此处跳过)")
        
        await shell.close()
        print("✅ 所有测试完成!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_conversation_selection()) 