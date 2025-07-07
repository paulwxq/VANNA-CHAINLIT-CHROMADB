"""
Redis集成修复验证测试

这个脚本用于快速验证Redis集成的修复是否有效
"""

import requests
import json
import time

def test_ask_agent_basic():
    """测试基本的ask_agent功能"""
    base_url = "http://localhost:8084/api/v0"
    
    print("=== Redis集成修复验证测试 ===\n")
    
    # 测试1：第一次请求（应该成功）
    print("1. 测试第一次请求...")
    print("   (注意：第一次请求可能需要较长时间，请耐心等待...)")
    response1 = requests.post(
        f"{base_url}/ask_agent",
        json={"question": "服务区有多少个？"},
        timeout=120  # 增加到120秒，适应较慢的响应
    )
    
    print(f"   状态码: {response1.status_code}")
    result1 = response1.json()
    print(f"   成功: {result1.get('success')}")
    print(f"   消息: {result1.get('message')}")
    
    if result1.get('success'):
        data = result1.get('data', {})
        print(f"   响应类型: {data.get('type')}")
        print(f"   响应文本: {data.get('response_text', '')[:50]}...")
        print(f"   是否缓存: {data.get('from_cache', False)}")
        print(f"   对话ID: {data.get('conversation_id')}")
    else:
        print(f"   错误: {json.dumps(result1, indent=2, ensure_ascii=False)}")
    
    # 等待一下
    time.sleep(1)
    
    # 测试2：第二次相同请求（应该使用缓存）
    print("\n2. 测试第二次请求（相同问题，应该使用缓存）...")
    response2 = requests.post(
        f"{base_url}/ask_agent",
        json={"question": "服务区有多少个？"},
        timeout=60  # 也增加超时时间，虽然缓存应该更快
    )
    
    print(f"   状态码: {response2.status_code}")
    result2 = response2.json()
    print(f"   成功: {result2.get('success')}")
    
    if result2.get('success'):
        data = result2.get('data', {})
        print(f"   是否缓存: {data.get('from_cache', False)}")
        print(f"   响应文本: {data.get('response_text', '')[:50]}...")
        
        # 验证缓存功能
        if data.get('from_cache'):
            print("\n✅ 缓存功能正常工作！")
        else:
            print("\n⚠️ 缓存功能可能有问题，第二次请求没有使用缓存")
    else:
        print(f"   错误: {json.dumps(result2, indent=2, ensure_ascii=False)}")
        print("\n❌ 第二次请求失败，可能是缓存格式问题")
    
    # 测试3：测试对话管理API
    print("\n3. 测试对话管理API...")
    try:
        stats_response = requests.get(f"{base_url}/conversation_stats", timeout=5)
        if stats_response.status_code == 200:
            stats = stats_response.json()
            if stats.get('success'):
                print("   ✅ 对话统计API正常")
                print(f"   总对话数: {stats.get('data', {}).get('total_conversations', 0)}")
                print(f"   总用户数: {stats.get('data', {}).get('total_users', 0)}")
            else:
                print("   ⚠️ 对话统计API返回失败")
        else:
            print(f"   ❌ 对话统计API错误: {stats_response.status_code}")
    except Exception as e:
        print(f"   ❌ 对话统计API异常: {str(e)}")
    
    print("\n=== 测试完成 ===")
    
    # 返回测试结果
    return {
        "first_request_success": result1.get('success', False),
        "second_request_success": result2.get('success', False),
        "cache_working": result2.get('data', {}).get('from_cache', False) if result2.get('success') else False
    }

if __name__ == "__main__":
    try:
        results = test_ask_agent_basic()
        
        print("\n测试结果汇总:")
        print(f"- 第一次请求: {'✅ 成功' if results['first_request_success'] else '❌ 失败'}")
        print(f"- 第二次请求: {'✅ 成功' if results['second_request_success'] else '❌ 失败'}")
        print(f"- 缓存功能: {'✅ 正常' if results['cache_working'] else '❌ 异常'}")
        
        if all(results.values()):
            print("\n🎉 所有测试通过！Redis集成修复成功！")
        else:
            print("\n❗ 部分测试失败，请检查日志")
            
    except Exception as e:
        print(f"\n❌ 测试异常: {str(e)}")
        print("请确保Flask服务正在运行 (python citu_app.py)") 