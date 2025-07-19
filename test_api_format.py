#!/usr/bin/env python3
"""
测试API响应格式是否符合标准化要求
验证是否包含 code 字段和其他必需字段
"""
import requests
import json
from datetime import datetime

def test_api_response_format():
    """测试API响应格式"""
    base_url = "http://localhost:8084"
    
    # 测试用例
    test_cases = [
        {
            "name": "获取用户对话列表",
            "url": f"{base_url}/api/v0/react/users/wang10/conversations?limit=3",
            "method": "GET"
        },
        {
            "name": "获取特定对话详情",
            "url": f"{base_url}/api/v0/react/users/wang10/conversations/wang10:20250717211620915",
            "method": "GET"
        }
    ]
    
    print(f"🧪 开始测试API响应格式 - {datetime.now()}")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 测试 {i}: {test_case['name']}")
        print(f"🔗 URL: {test_case['url']}")
        
        try:
            response = requests.get(test_case['url'], timeout=30)
            
            print(f"📊 HTTP状态码: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    print(f"✅ JSON解析成功")
                    
                    # 检查必需字段
                    required_fields = ["code", "success", "message", "data"]
                    missing_fields = []
                    
                    for field in required_fields:
                        if field not in data:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        print(f"❌ 缺少必需字段: {missing_fields}")
                    else:
                        print(f"✅ 所有必需字段都存在")
                        
                        # 显示关键字段值
                        print(f"📋 响应字段:")
                        print(f"   - code: {data.get('code')}")
                        print(f"   - success: {data.get('success')}")
                        print(f"   - message: {data.get('message')}")
                        print(f"   - data类型: {type(data.get('data'))}")
                        
                        if 'data' in data and isinstance(data['data'], dict):
                            data_keys = list(data['data'].keys())
                            print(f"   - data字段: {data_keys}")
                    
                    # 显示完整响应（格式化）
                    print(f"\n📄 完整响应:")
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    print(f"📄 原始响应: {response.text}")
            else:
                print(f"❌ HTTP请求失败")
                print(f"📄 响应内容: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求异常: {e}")
        
        print("-" * 40)
    
    print(f"\n🏁 测试完成 - {datetime.now()}")

if __name__ == "__main__":
    test_api_response_format() 