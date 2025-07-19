#!/usr/bin/env python3
"""
测试新的API实现
"""
import requests
import json
from datetime import datetime

def test_api():
    """测试新的API端点"""
    print("=" * 60)
    print("测试新的API实现")
    print("=" * 60)
    
    base_url = "http://localhost:8084"
    thread_id = "wang10:20250717211620915"
    user_id = "wang10"
    
    # 测试不包含工具消息的API
    print(f"\n🚀 测试API (不包含工具消息)...")
    url = f"{base_url}/api/v0/react/users/{user_id}/conversations/{thread_id}"
    
    try:
        response = requests.get(url, timeout=30)
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API调用成功")
            print(f"📝 响应结构:")
            print(f"  success: {data.get('success')}")
            print(f"  timestamp: {data.get('timestamp')}")
            
            if 'data' in data:
                api_data = data['data']
                print(f"  data.user_id: {api_data.get('user_id')}")
                print(f"  data.thread_id: {api_data.get('thread_id')}")
                print(f"  data.message_count: {api_data.get('message_count')}")
                print(f"  data.created_at: {api_data.get('created_at')}")
                print(f"  data.total_checkpoints: {api_data.get('total_checkpoints')}")
                
                messages = api_data.get('messages', [])
                print(f"\n📋 前3条消息:")
                for i, msg in enumerate(messages[:3]):
                    print(f"  消息 {i+1}:")
                    print(f"    id: {msg.get('id')}")
                    print(f"    type: {msg.get('type')}")
                    print(f"    timestamp: {msg.get('timestamp')}")
                    print(f"    content: {msg.get('content', '')[:50]}...")
            
            # 保存完整响应到文件
            with open('api_response_no_tools.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整响应已保存到 api_response_no_tools.json")
            
        else:
            print(f"❌ API调用失败")
            print(f"响应内容: {response.text}")
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    
    # 测试包含工具消息的API
    print(f"\n🚀 测试API (包含工具消息)...")
    url_with_tools = f"{base_url}/api/v0/react/users/{user_id}/conversations/{thread_id}?include_tools=true"
    
    try:
        response = requests.get(url_with_tools, timeout=30)
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API调用成功")
            
            if 'data' in data:
                api_data = data['data']
                messages = api_data.get('messages', [])
                print(f"📝 包含工具消息的总数: {len(messages)}")
                
                # 统计消息类型
                type_counts = {}
                for msg in messages:
                    msg_type = msg.get('type', 'unknown')
                    type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
                
                print(f"📊 消息类型统计:")
                for msg_type, count in type_counts.items():
                    print(f"  {msg_type}: {count}")
            
            # 保存完整响应到文件
            with open('api_response_with_tools.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整响应已保存到 api_response_with_tools.json")
            
        else:
            print(f"❌ API调用失败")
            print(f"响应内容: {response.text}")
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    test_api() 