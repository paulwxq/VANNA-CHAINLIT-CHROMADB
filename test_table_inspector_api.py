#!/usr/bin/env python3
"""
表检查API测试脚本

用于测试新实现的表列表获取API功能
"""

import requests
import json

# 测试配置
API_BASE_URL = "http://localhost:8084"
ENDPOINT = "/api/v0/database/tables"

def test_get_tables():
    """测试获取表列表API"""
    
    # 测试数据
    test_cases = [
        {
            "name": "测试默认schema（public）",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db"
            },
            "expected_schemas": ["public"]
        },
        {
            "name": "测试指定单个schema",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "schema": "public"
            },
            "expected_schemas": ["public"]
        },
        {
            "name": "测试多个schema",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "schema": "public,information_schema"
            },
            "expected_schemas": ["public", "information_schema"]
        },
        {
            "name": "测试空schema参数",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "schema": ""
            },
            "expected_schemas": ["public"]
        }
    ]
    
    print("🧪 开始测试表检查API")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 30)
        
        try:
            # 发送请求
            response = requests.post(
                f"{API_BASE_URL}{ENDPOINT}",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"📤 请求: {json.dumps(test_case['payload'], ensure_ascii=False)}")
            print(f"📊 状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    result_data = data.get("data", {})
                    tables = result_data.get("tables", [])
                    schemas = result_data.get("schemas", [])
                    
                    print(f"✅ 成功")
                    print(f"📋 返回表数量: {len(tables)}")
                    print(f"🏷️  查询的schemas: {schemas}")
                    print(f"📝 前5个表: {tables[:5]}")
                    
                    # 验证schema
                    if schemas == test_case["expected_schemas"]:
                        print(f"✅ Schema验证通过")
                    else:
                        print(f"❌ Schema验证失败: 期望{test_case['expected_schemas']}, 实际{schemas}")
                        
                else:
                    print(f"❌ API返回失败: {data.get('message')}")
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   错误信息: {error_data.get('message', 'N/A')}")
                except:
                    print(f"   响应内容: {response.text}")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求异常: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")

def test_error_cases():
    """测试错误情况"""
    
    print("\n\n🚨 测试错误情况")
    print("=" * 50)
    
    error_test_cases = [
        {
            "name": "缺少db_connection参数",
            "payload": {
                "schema": "public"
            },
            "expected_status": 400
        },
        {
            "name": "无效的数据库连接",
            "payload": {
                "db_connection": "postgresql://invalid:invalid@localhost:5432/invalid"
            },
            "expected_status": 500
        }
    ]
    
    for i, test_case in enumerate(error_test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 30)
        
        try:
            response = requests.post(
                f"{API_BASE_URL}{ENDPOINT}",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"📤 请求: {json.dumps(test_case['payload'], ensure_ascii=False)}")
            print(f"📊 状态码: {response.status_code}")
            
            if response.status_code == test_case["expected_status"]:
                print(f"✅ 错误处理正确")
            else:
                print(f"❌ 期望状态码{test_case['expected_status']}, 实际{response.status_code}")
                
            # 显示错误信息
            try:
                error_data = response.json()
                print(f"📄 错误信息: {error_data.get('message', 'N/A')}")
            except:
                print(f"📄 响应内容: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            print(f"⏰ 请求超时（这是预期的，对于无效连接）")
        except Exception as e:
            print(f"❌ 异常: {e}")

def test_get_table_ddl():
    """测试获取表DDL API"""
    
    print("\n\n🧪 测试表DDL生成API")
    print("=" * 50)
    
    # 测试数据
    test_cases = [
        {
            "name": "测试DDL格式输出",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.bss_company",
                "business_context": "高速公路服务区管理系统",
                "type": "ddl"
            }
        },
        {
            "name": "测试MD格式输出",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.bss_company",
                "business_context": "高速公路服务区管理系统",
                "type": "md"
            }
        },
        {
            "name": "测试同时输出DDL和MD",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.bss_company",
                "business_context": "高速公路服务区管理系统",
                "type": "both"
            }
        },
        {
            "name": "测试不指定业务上下文",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.bss_company",
                "type": "ddl"
            }
        }
    ]
    
    endpoint = "/api/v0/database/table/ddl"
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 30)
        
        try:
            # 发送请求
            response = requests.post(
                f"{API_BASE_URL}{endpoint}",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=60  # DDL生成可能需要更长时间（LLM调用）
            )
            
            print(f"📤 请求: {json.dumps(test_case['payload'], ensure_ascii=False)}")
            print(f"📊 状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    result_data = data.get("data", {})
                    table_info = result_data.get("table_info", {})
                    generation_info = result_data.get("generation_info", {})
                    
                    print(f"✅ 成功")
                    print(f"📋 表信息: {table_info.get('full_name')} ({table_info.get('field_count')}字段)")
                    print(f"💡 生成信息: {generation_info}")
                    
                    # 检查输出内容
                    output_type = test_case["payload"].get("type", "ddl")
                    if output_type in ["ddl", "both"] and "ddl" in result_data:
                        ddl_lines = result_data["ddl"].count('\n')
                        print(f"🔧 DDL内容: {ddl_lines}行")
                        # 显示DDL的前几行
                        ddl_preview = '\n'.join(result_data["ddl"].split('\n')[:3])
                        print(f"   预览: {ddl_preview}...")
                    
                    if output_type in ["md", "both"] and "md" in result_data:
                        md_lines = result_data["md"].count('\n')
                        print(f"📄 MD内容: {md_lines}行")
                        # 显示MD的标题行
                        md_lines_list = result_data["md"].split('\n')
                        if md_lines_list:
                            print(f"   标题: {md_lines_list[0]}")
                    
                    if "fields" in result_data:
                        print(f"🗂️  字段数量: {len(result_data['fields'])}")
                        
                else:
                    print(f"❌ API返回失败: {data.get('message')}")
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   错误信息: {error_data.get('message', 'N/A')}")
                except:
                    print(f"   响应内容: {response.text[:200]}")
                    
        except requests.exceptions.Timeout:
            print(f"⏰ 请求超时（LLM处理可能需要较长时间）")
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求异常: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")

def test_ddl_error_cases():
    """测试DDL API的错误情况"""
    
    print("\n\n🚨 测试DDL API错误情况")
    print("=" * 50)
    
    endpoint = "/api/v0/database/table/ddl"
    error_test_cases = [
        {
            "name": "缺少db_connection参数",
            "payload": {
                "table": "public.test"
            },
            "expected_status": 400
        },
        {
            "name": "缺少table参数",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db"
            },
            "expected_status": 400
        },
        {
            "name": "无效的type参数",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.test",
                "type": "invalid"
            },
            "expected_status": 400
        },
        {
            "name": "不存在的表",
            "payload": {
                "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
                "table": "public.non_existent_table_12345"
            },
            "expected_status": 500
        }
    ]
    
    for i, test_case in enumerate(error_test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 30)
        
        try:
            response = requests.post(
                f"{API_BASE_URL}{endpoint}",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"📤 请求: {json.dumps(test_case['payload'], ensure_ascii=False)}")
            print(f"📊 状态码: {response.status_code}")
            
            if response.status_code == test_case["expected_status"]:
                print(f"✅ 错误处理正确")
            else:
                print(f"❌ 期望状态码{test_case['expected_status']}, 实际{response.status_code}")
                
            # 显示错误信息
            try:
                error_data = response.json()
                print(f"📄 错误信息: {error_data.get('message', 'N/A')}")
            except:
                print(f"📄 响应内容: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            print(f"⏰ 请求超时（这可能是预期的）")
        except Exception as e:
            print(f"❌ 异常: {e}")

if __name__ == "__main__":
    print("🚀 表检查API测试开始")
    print(f"🌐 API地址: {API_BASE_URL}")
    
    # 首先测试表列表API
    test_get_tables()
    
    # 然后测试表列表API的错误情况
    test_error_cases()
    
    # 测试DDL生成API
    test_get_table_ddl()
    
    # 测试DDL API的错误情况
    test_ddl_error_cases()
    
    print("\n" + "=" * 50)
    print("🏁 所有测试完成")
    print("\n💡 使用说明:")
    print("   - 表列表API: POST /api/v0/database/tables")
    print("   - 表DDL API: POST /api/v0/database/table/ddl")
    print("   - 如果看到连接错误，请确保数据库服务器可访问")
    print("   - DDL生成包含LLM调用，可能需要较长时间")
    print("   - 支持三种输出格式：ddl、md、both") 