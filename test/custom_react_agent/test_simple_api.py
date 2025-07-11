import requests
import json
import time

def test_api():
    base_url = "http://localhost:5000"
    
    # 测试简单同步版本
    print("=== 测试简单同步版本 ===")
    try:
        response = requests.get(f"{base_url}/api/test/users/wang/conversations?limit=5")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"测试失败: {e}")
    
    print("\n=== 测试标准版本 ===")
    try:
        response = requests.get(f"{base_url}/api/users/wang/conversations?limit=5")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"测试失败: {e}")

if __name__ == "__main__":
    test_api() 