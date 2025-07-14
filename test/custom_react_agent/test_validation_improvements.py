#!/usr/bin/env python3
"""
测试 API 参数验证和错误处理改进
验证JSON格式错误处理和用户ID一致性校验
"""

import requests
import json

def test_validation_improvements():
    """测试参数验证改进"""
    
    api_url = "http://localhost:8000/api/chat"
    
    print("🧪 开始测试 API 参数验证改进...")
    print("=" * 80)
    
    # 测试用例1: JSON格式错误 - 尾随逗号
    print(f"\n📋 测试用例1: JSON格式错误（尾随逗号）")
    malformed_json = '{ "question": "测试问题", "user_id": "wang01", "thread_id": "wang01:20250714102158117", }'
    try:
        response = requests.post(
            api_url,
            data=malformed_json,  # 使用data而不是json，模拟原始JSON字符串
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📊 响应状态码: {response.status_code}")
        result = response.json()
        print(f"📝 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        # 验证是否是400错误且有明确的错误信息
        if response.status_code == 400 and "JSON格式" in result.get("error", ""):
            print("✅ JSON格式错误处理正确")
        else:
            print("❌ JSON格式错误处理有问题")
            
    except Exception as e:
        print(f"❌ 测试JSON格式错误失败: {e}")
    
    # 测试用例2: 用户ID不一致 - thread_id
    print(f"\n📋 测试用例2: 用户ID不一致（thread_id）")
    test_case_2 = {
        "question": "测试用户ID不一致",
        "user_id": "alice",
        "thread_id": "bob:20250714120000001"  # 用户ID不匹配
    }
    try:
        response = requests.post(
            api_url,
            json=test_case_2,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📊 响应状态码: {response.status_code}")
        result = response.json()
        print(f"📝 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        # 验证是否正确检测到用户ID不一致
        if response.status_code == 400 and "会话归属验证失败" in result.get("error", ""):
            print("✅ 用户ID一致性校验正确")
        else:
            print("❌ 用户ID一致性校验有问题")
            
    except Exception as e:
        print(f"❌ 测试用户ID一致性失败: {e}")
    
    # 测试用例3: 用户ID不一致 - conversation_id
    print(f"\n📋 测试用例3: 用户ID不一致（conversation_id）")
    test_case_3 = {
        "question": "测试conversation_id用户ID不一致",
        "user_id": "charlie",
        "conversation_id": "david:20250714120000002"  # 用户ID不匹配
    }
    try:
        response = requests.post(
            api_url,
            json=test_case_3,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📊 响应状态码: {response.status_code}")
        result = response.json()
        print(f"📝 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if response.status_code == 400 and "会话归属验证失败" in result.get("error", ""):
            print("✅ conversation_id用户ID一致性校验正确")
        else:
            print("❌ conversation_id用户ID一致性校验有问题")
            
    except Exception as e:
        print(f"❌ 测试conversation_id用户ID一致性失败: {e}")
    
    # 测试用例4: 会话ID格式错误
    print(f"\n📋 测试用例4: 会话ID格式错误（缺少冒号）")
    test_case_4 = {
        "question": "测试会话ID格式错误",
        "user_id": "eve",
        "thread_id": "eve20250714120000003"  # 缺少冒号
    }
    try:
        response = requests.post(
            api_url,
            json=test_case_4,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📊 响应状态码: {response.status_code}")
        result = response.json()
        print(f"📝 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if response.status_code == 400 and "会话ID格式无效" in result.get("error", ""):
            print("✅ 会话ID格式校验正确")
        else:
            print("❌ 会话ID格式校验有问题")
            
    except Exception as e:
        print(f"❌ 测试会话ID格式错误失败: {e}")
    
    # 测试用例5: 正常情况 - 验证修改不影响正常流程
    print(f"\n📋 测试用例5: 正常情况（验证修改不影响正常流程）")
    test_case_5 = {
        "question": "这是一个正常的测试问题",
        "user_id": "frank",
        "thread_id": "frank:20250714120000005"
    }
    try:
        response = requests.post(
            api_url,
            json=test_case_5,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 正常请求处理成功")
            print(f"   - conversation_id: {result.get('data', {}).get('conversation_id')}")
            print(f"   - user_id: {result.get('data', {}).get('user_id')}")
        else:
            print(f"❌ 正常请求处理失败: {response.text}")
            
    except Exception as e:
        print(f"❌ 测试正常情况失败: {e}")
    
    # 测试用例6: guest用户不受限制
    print(f"\n📋 测试用例6: guest用户不受会话ID限制")
    test_case_6 = {
        "question": "guest用户测试",
        "user_id": "guest",
        "thread_id": "someuser:20250714120000006"  # guest用户应该不受限制
    }
    try:
        response = requests.post(
            api_url,
            json=test_case_6,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ guest用户不受会话ID限制，处理正确")
        else:
            result = response.json()
            print(f"❌ guest用户处理有问题: {result}")
            
    except Exception as e:
        print(f"❌ 测试guest用户失败: {e}")
    
    print("\n" + "=" * 80)
    print("🎯 测试完成！")
    print("\n💡 预期结果总结:")
    print("1. JSON格式错误应该返回400错误，明确指出JSON格式问题")
    print("2. 用户ID与thread_id/conversation_id不一致应该返回400错误")
    print("3. 会话ID格式错误应该返回400错误")
    print("4. 正常请求应该不受影响")
    print("5. guest用户不受会话ID限制")

def test_edge_cases():
    """测试边界情况"""
    
    api_url = "http://localhost:8000/api/chat"
    
    print("\n🔍 测试边界情况...")
    print("-" * 60)
    
    # 边界情况1: 复杂的会话ID格式
    test_edge_1 = {
        "question": "测试复杂会话ID",
        "user_id": "user:with:colons",
        "thread_id": "user:with:colons:20250714120000001:extra"
    }
    
    try:
        response = requests.post(api_url, json=test_edge_1, timeout=10)
        print(f"🔬 复杂会话ID测试 - 状态码: {response.status_code}")
        if response.status_code == 200:
            print("✅ 复杂会话ID处理正确")
        else:
            result = response.json()
            print(f"📝 错误信息: {result.get('error', '')}")
    except Exception as e:
        print(f"❌ 复杂会话ID测试失败: {e}")

if __name__ == "__main__":
    test_validation_improvements()
    test_edge_cases()