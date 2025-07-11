#!/usr/bin/env python3
"""
测试新增的对话历史查询API
"""

import requests
import json
import time
import sys
from typing import Dict, Any

API_BASE = "http://localhost:8000"

def test_health_check():
    """测试健康检查"""
    print("🔍 测试健康检查...")
    try:
        response = requests.get(f"{API_BASE}/health")
        result = response.json()
        
        if response.status_code == 200 and result.get("status") == "healthy":
            print("✅ 健康检查通过")
            return True
        else:
            print(f"❌ 健康检查失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

def create_test_conversations(user_id: str) -> list:
    """创建测试对话"""
    print(f"\n💬 为用户 {user_id} 创建测试对话...")
    
    test_questions = [
        "请问哪个高速服务区的档口数量最多？",
        "南城服务区有多少个餐饮档口？",
        "请查询收入最高的服务区",
        "你好，请介绍一下系统功能"
    ]
    
    thread_ids = []
    
    for i, question in enumerate(test_questions):
        print(f"  📝 创建对话 {i+1}: {question[:30]}...")
        
        try:
            response = requests.post(
                f"{API_BASE}/api/chat",
                json={
                    "question": question,
                    "user_id": user_id
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    thread_id = result.get("thread_id")
                    thread_ids.append(thread_id)
                    print(f"     ✅ 创建成功: {thread_id}")
                else:
                    print(f"     ❌ 创建失败: {result.get('error')}")
            else:
                print(f"     ❌ HTTP错误: {response.status_code}")
                
            # 稍微延迟，确保时间戳不同
            time.sleep(1)
            
        except Exception as e:
            print(f"     ❌ 异常: {e}")
    
    print(f"🎯 共创建了 {len(thread_ids)} 个测试对话")
    return thread_ids

def test_get_user_conversations(user_id: str, limit: int = 5):
    """测试获取用户对话列表"""
    print(f"\n📋 测试获取用户 {user_id} 的对话列表 (limit={limit})...")
    
    try:
        response = requests.get(f"{API_BASE}/api/users/{user_id}/conversations?limit={limit}")
        
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", {})
                conversations = data.get("conversations", [])
                
                print(f"✅ 成功获取 {len(conversations)} 个对话")
                print(f"   用户ID: {data.get('user_id')}")
                print(f"   总数量: {data.get('total_count')}")
                print(f"   限制数量: {data.get('limit')}")
                
                # 显示对话列表
                for i, conv in enumerate(conversations):
                    print(f"\n   📝 对话 {i+1}:")
                    print(f"      Thread ID: {conv.get('thread_id')}")
                    print(f"      时间戳: {conv.get('formatted_time')}")
                    print(f"      消息数: {conv.get('message_count')}")
                    print(f"      预览: {conv.get('conversation_preview')}")
                    print(f"      最后消息: {conv.get('last_message', '')[:50]}...")
                
                return conversations
            else:
                print(f"❌ API返回错误: {result.get('error')}")
                return []
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   错误详情: {error_detail}")
            except:
                print(f"   响应内容: {response.text}")
            return []
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return []

def test_get_conversation_detail(user_id: str, thread_id: str):
    """测试获取对话详情"""
    print(f"\n📖 测试获取对话详情: {thread_id}...")
    
    try:
        response = requests.get(f"{API_BASE}/api/users/{user_id}/conversations/{thread_id}")
        
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", {})
                messages = data.get("messages", [])
                
                print(f"✅ 成功获取对话详情")
                print(f"   用户ID: {data.get('user_id')}")
                print(f"   Thread ID: {data.get('thread_id')}")
                print(f"   消息数量: {data.get('message_count')}")
                
                # 显示消息历史
                print(f"\n   📜 消息历史:")
                for i, msg in enumerate(messages):
                    msg_type = msg.get('type', 'unknown')
                    content = msg.get('content', '')
                    
                    # 限制显示长度
                    display_content = content[:100] + "..." if len(content) > 100 else content
                    
                    print(f"      [{i+1}] {msg_type.upper()}: {display_content}")
                    
                    # 如果有工具调用，显示相关信息
                    if msg.get('tool_calls'):
                        print(f"          🔧 包含工具调用")
                
                return data
            else:
                print(f"❌ API返回错误: {result.get('error')}")
                return None
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   错误详情: {error_detail}")
            except:
                print(f"   响应内容: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None

def test_invalid_cases(user_id: str):
    """测试无效情况的处理"""
    print(f"\n⚠️  测试错误处理...")
    
    # 测试1: 不存在的用户
    print("   测试不存在的用户...")
    response = requests.get(f"{API_BASE}/api/users/nonexistent_user/conversations")
    print(f"   状态码: {response.status_code} (应该是200，返回空列表)")
    
    # 测试2: 不匹配的thread_id
    print("   测试不匹配的thread_id...")
    response = requests.get(f"{API_BASE}/api/users/{user_id}/conversations/wronguser:20250115103000001")
    print(f"   状态码: {response.status_code} (应该是400)")
    
    # 测试3: 超出限制的limit参数
    print("   测试超出限制的limit参数...")
    response = requests.get(f"{API_BASE}/api/users/{user_id}/conversations?limit=100")
    if response.status_code == 200:
        result = response.json()
        actual_limit = result.get("data", {}).get("limit", 0)
        print(f"   实际limit: {actual_limit} (应该被限制为50)")

def main():
    """主测试流程"""
    print("🚀 开始测试对话历史查询API")
    print("=" * 60)
    
    # 1. 健康检查
    if not test_health_check():
        print("❌ 服务不可用，退出测试")
        sys.exit(1)
    
    # 2. 设置测试用户
    user_id = "test_user"
    print(f"\n🎯 使用测试用户: {user_id}")
    
    # 3. 创建测试对话
    thread_ids = create_test_conversations(user_id)
    
    if not thread_ids:
        print("❌ 未能创建测试对话，跳过后续测试")
        return
    
    # 4. 测试获取对话列表
    conversations = test_get_user_conversations(user_id, limit=3)
    
    # 5. 测试获取对话详情
    if conversations and len(conversations) > 0:
        test_thread_id = conversations[0].get("thread_id")
        test_get_conversation_detail(user_id, test_thread_id)
    
    # 6. 测试边界情况
    test_invalid_cases(user_id)
    
    print("\n🎉 测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    main() 