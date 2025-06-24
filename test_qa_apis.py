#!/usr/bin/env python
"""
QA反馈API测试脚本
用于验证所有API端点是否正常工作
"""

import requests
import json

# 配置
BASE_URL = "http://localhost:8084"  # 根据你的端口配置
API_PREFIX = "/api/v0/qa_feedback"

def test_api(method, endpoint, data=None, expected_status=200):
    """测试API端点"""
    url = f"{BASE_URL}{API_PREFIX}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data, headers={'Content-Type': 'application/json'})
        elif method == "PUT":
            response = requests.put(url, json=data, headers={'Content-Type': 'application/json'})
        elif method == "DELETE":
            response = requests.delete(url)
        
        print(f"\n{'='*60}")
        print(f"测试: {method} {endpoint}")
        print(f"URL: {url}")
        print(f"状态码: {response.status_code}")
        print(f"响应:")
        try:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        except:
            print(response.text)
        
        return response.status_code == expected_status
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试QA反馈模块API...")
    
    # 1. 测试统计API (GET)
    print("\n📊 测试统计API")
    test_api("GET", "/stats")
    
    # 2. 测试查询API (POST)
    print("\n🔍 测试查询API")
    test_api("POST", "/query", {
        "page": 1,
        "page_size": 10
    })
    
    # 3. 测试添加反馈API (POST)
    print("\n➕ 测试添加反馈API")
    add_result = test_api("POST", "/add", {
        "question": "测试问题",
        "sql": "SELECT 1 as test",
        "is_thumb_up": True,
        "user_id": "test_user"
    })
    
    # 4. 测试训练API (POST) - 重点测试
    print("\n⭐ 测试训练API (重点)")
    test_api("POST", "/add_to_training", {
        "feedback_ids": [1, 2, 3]
    }, expected_status=404)  # 可能没有这些ID，但API应该存在
    
    # 5. 测试更新API (PUT)
    print("\n✏️ 测试更新API")
    test_api("PUT", "/update/1", {
        "question": "更新的问题"
    }, expected_status=404)  # 可能没有ID=1的记录
    
    # 6. 测试删除API (DELETE)
    print("\n🗑️ 测试删除API")
    test_api("DELETE", "/delete/999", expected_status=404)  # 测试不存在的ID
    
    print(f"\n{'='*60}")
    print("🎯 测试完成！")
    print("📝 重点关注训练API是否返回正确的错误信息而不是'API not ported'")

if __name__ == "__main__":
    main() 