#!/usr/bin/env python3
"""
测试Event loop修复效果
"""
import requests
import json

def test_fixed_api():
    """测试修复后的API"""
    print("🔍 测试修复后的API:")
    print("=" * 40)
    
    # 测试用户提到的成功案例
    print("根据用户反馈，对话列表API应该是正常工作的...")
    print("但我的测试一直显示0个对话，让我们看看实际情况:")
    
    # 1. 测试对话列表
    print("\n1. 对话列表API...")
    try:
        response = requests.get('http://localhost:8000/api/v0/react/users/doudou/conversations')
        print(f"   状态: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            conversations = data.get("data", {}).get("conversations", [])
            total_count = data.get("data", {}).get("total_count", 0)
            success = data.get("success", False)
            
            print(f"   成功标志: {success}")
            print(f"   对话数量: {len(conversations)}")
            print(f"   total_count: {total_count}")
            
            if conversations:
                print(f"   ✅ 找到对话!")
                print(f"   首个对话: {conversations[0]['thread_id']}")
                print(f"   对话预览: {conversations[0].get('conversation_preview', 'N/A')}")
            else:
                print(f"   ❌ 未找到对话（但用户说应该有1个对话）")
        else:
            print(f"   错误: {response.json()}")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    
    print("\n" + "=" * 40)
    print("用户看到的结果：1个对话，包含preview等完整信息")
    print("我看到的结果：0个对话")
    print("可能的原因：服务器重启后Agent状态变化，或者我的测试时机有问题")
    
    # 先跳过对话详情测试，专注解决不一致问题
    print("\n暂时跳过对话详情API测试，优先解决对话列表结果不一致的问题")

if __name__ == "__main__":
    test_fixed_api() 