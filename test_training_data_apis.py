#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
训练数据管理API测试脚本
用于测试新增的训练数据管理接口
"""

import requests
import json
import sys

# API基础URL
BASE_URL = "http://localhost:8084"
API_PREFIX = "/api/v0/training_data"

def test_api(method: str, endpoint: str, data=None, expected_status=200):
    """测试API的通用函数"""
    url = f"{BASE_URL}{API_PREFIX}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data, headers={'Content-Type': 'application/json'})
        elif method == "DELETE":
            response = requests.delete(url, json=data, headers={'Content-Type': 'application/json'})
        else:
            print(f"❌ 不支持的HTTP方法: {method}")
            return False
        
        print(f"📤 {method} {endpoint}")
        if data:
            print(f"📋 请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        print(f"📥 状态码: {response.status_code}")
        
        if response.status_code == expected_status:
            print("✅ 状态码正确")
        else:
            print(f"⚠️ 期望状态码: {expected_status}, 实际状态码: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"📄 响应: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
            return True
        except:
            print(f"📄 响应: {response.text}")
            return False
            
    except requests.ConnectionError:
        print(f"❌ 连接失败: 请确保服务器运行在 {BASE_URL}")
        return False
    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试训练数据管理API...")
    print(f"🔗 服务器地址: {BASE_URL}")
    print("="*60)
    
    # 1. 测试统计API (GET)
    print("\n📊 测试统计API")
    test_api("GET", "/stats")
    
    # 2. 测试查询API (POST) - 基础查询
    print("\n🔍 测试查询API - 基础查询")
    test_api("POST", "/query", {
        "page": 1,
        "page_size": 10
    })
    
    # 3. 测试查询API (POST) - 带筛选
    print("\n🔍 测试查询API - 带筛选")
    test_api("POST", "/query", {
        "page": 1,
        "page_size": 5,
        "training_data_type": "sql",
        "search_keyword": "用户"
    })
    
    # 4. 测试创建API (POST) - 单条SQL记录
    print("\n➕ 测试创建API - 单条SQL记录")
    test_api("POST", "/create", {
        "data": {
            "training_data_type": "sql",
            "question": "查询所有测试用户",
            "sql": "SELECT * FROM users WHERE status = 'test'"
        }
    })
    
    # 5. 测试创建API (POST) - 批量记录
    print("\n➕ 测试创建API - 批量记录")
    test_api("POST", "/create", {
        "data": [
            {
                "training_data_type": "documentation",
                "content": "这是一个测试文档，用于说明用户表的结构和用途。"
            },
            {
                "training_data_type": "ddl",
                "ddl": "CREATE TABLE test_table (id INT PRIMARY KEY, name VARCHAR(100));"
            }
        ]
    })
    
    # 6. 测试创建API (POST) - SQL语法错误
    print("\n➕ 测试创建API - SQL语法错误")
    test_api("POST", "/create", {
        "data": {
            "training_data_type": "sql",
            "question": "测试错误SQL",
            "sql": "INVALID SQL SYNTAX"
        }
    }, expected_status=200)  # 批量操作中的错误仍返回200，但results中会有错误信息
    
    # 6.1. 测试创建API (POST) - 危险SQL操作检查
    print("\n➕ 测试创建API - 危险SQL操作检查")
    test_api("POST", "/create", {
        "data": [
            {
                "training_data_type": "sql",
                "question": "测试UPDATE操作",
                "sql": "UPDATE users SET status = 'inactive' WHERE id = 1"
            },
            {
                "training_data_type": "sql",
                "question": "测试DELETE操作",
                "sql": "DELETE FROM users WHERE id = 1"
            },
            {
                "training_data_type": "sql",
                "question": "测试DROP操作",
                "sql": "DROP TABLE test_table"
            }
        ]
    }, expected_status=200)  # 批量操作返回200，但会有错误信息
    
    # 7. 测试删除API (POST) - 不存在的ID
    print("\n🗑️ 测试删除API - 不存在的ID")
    test_api("POST", "/delete", {
        "ids": ["non-existent-id-1", "non-existent-id-2"],
        "confirm": True
    })
    
    # 8. 测试删除API (POST) - 缺少确认
    print("\n🗑️ 测试删除API - 缺少确认")
    test_api("POST", "/delete", {
        "ids": ["test-id"],
        "confirm": False
    }, expected_status=400)
    
    # 9. 测试参数验证 - 页码错误
    print("\n⚠️ 测试参数验证 - 页码错误")
    test_api("POST", "/query", {
        "page": 0,
        "page_size": 10
    }, expected_status=400)
    
    # 10. 测试参数验证 - 页面大小错误
    print("\n⚠️ 测试参数验证 - 页面大小错误")
    test_api("POST", "/query", {
        "page": 1,
        "page_size": 150
    }, expected_status=400)
    
    print(f"\n{'='*60}")
    print("🎯 测试完成！")
    print("\n📝 说明：")
    print("- ✅ 表示API响应正常")
    print("- ⚠️ 表示状态码不符合预期")
    print("- ❌ 表示连接或请求失败")
    print("\n💡 提示：")
    print("- 首次运行时可能没有训练数据，这是正常的")
    print("- 创建操作成功后，再次查询可以看到新增的数据")
    print("- 删除不存在的ID会返回成功，但failed_count会显示失败数量")

if __name__ == "__main__":
    main() 