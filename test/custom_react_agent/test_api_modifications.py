#!/usr/bin/env python3
"""
测试 API 修改是否正确实现
测试新增的 conversation_id 和 user_id 字段
"""

import requests
import json

def test_api_modifications():
    """测试API修改"""
    
    api_url = "http://localhost:8000/api/chat"
    
    # 测试用例1: 使用 thread_id (原有方式)
    test_case_1 = {
        "question": "测试使用thread_id参数",
        "user_id": "test_user_1",
        "thread_id": "test_user_1:20250714120000001"
    }
    
    # 测试用例2: 使用 conversation_id (新增方式)
    test_case_2 = {
        "question": "测试使用conversation_id参数", 
        "user_id": "test_user_2",
        "conversation_id": "test_user_2:20250714120000002"
    }
    
    # 测试用例3: 同时提供两个参数 (应该优先使用thread_id)
    test_case_3 = {
        "question": "测试同时提供两个参数",
        "user_id": "test_user_3", 
        "thread_id": "test_user_3:20250714120000003",
        "conversation_id": "test_user_3:20250714120000004"  # 这个应该被忽略
    }
    
    # 测试用例4: 都不提供 (应该自动生成)
    test_case_4 = {
        "question": "测试自动生成会话ID",
        "user_id": "test_user_4"
    }
    
    test_cases = [
        ("使用thread_id", test_case_1),
        ("使用conversation_id", test_case_2), 
        ("同时提供两个参数", test_case_3),
        ("自动生成", test_case_4)
    ]
    
    print("🧪 开始测试 API 修改...")
    print("=" * 60)
    
    for test_name, test_data in test_cases:
        print(f"\n📋 测试用例: {test_name}")
        print(f"📨 请求数据: {json.dumps(test_data, ensure_ascii=False, indent=2)}")
        
        try:
            response = requests.post(
                api_url,
                json=test_data,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"📊 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                
                # 检查必需的新字段
                conversation_id = data.get("conversation_id")
                user_id = data.get("user_id") 
                thread_id = data.get("react_agent_meta", {}).get("thread_id")
                
                print(f"✅ 响应成功:")
                print(f"   - conversation_id: {conversation_id}")
                print(f"   - user_id: {user_id}")
                print(f"   - thread_id: {thread_id}")
                print(f"   - conversation_id == thread_id: {conversation_id == thread_id}")
                print(f"   - user_id 正确: {user_id == test_data['user_id']}")
                
                # 验证逻辑正确性
                if test_name == "同时提供两个参数":
                    expected_thread_id = test_data["thread_id"]
                    if thread_id == expected_thread_id:
                        print(f"   ✅ 优先使用 thread_id 逻辑正确")
                    else:
                        print(f"   ❌ 优先使用 thread_id 逻辑错误，期望: {expected_thread_id}, 实际: {thread_id}")
                
                elif test_name == "使用conversation_id":
                    expected_thread_id = test_data["conversation_id"]
                    if thread_id == expected_thread_id:
                        print(f"   ✅ conversation_id 转换为 thread_id 逻辑正确")
                    else:
                        print(f"   ❌ conversation_id 转换逻辑错误，期望: {expected_thread_id}, 实际: {thread_id}")
                
            else:
                print(f"❌ 请求失败: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络错误: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 测试完成！")
    print("\n💡 预期结果:")
    print("1. 所有响应都应该包含 conversation_id 和 user_id 字段")
    print("2. conversation_id 应该等于 react_agent_meta.thread_id")
    print("3. user_id 应该等于请求中的 user_id")
    print("4. 当同时提供 thread_id 和 conversation_id 时，应该优先使用 thread_id")
    print("5. 当只提供 conversation_id 时，应该将其作为 thread_id 使用")

if __name__ == "__main__":
    test_api_modifications()