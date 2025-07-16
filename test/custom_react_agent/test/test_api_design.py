#!/usr/bin/env python3
"""
测试修改后的 API 是否符合设计文档要求
"""
import json
import asyncio
import aiohttp
from typing import Dict, Any

async def test_api_design_compliance():
    """测试 API 设计文档合规性"""
    
    base_url = "http://localhost:8000"
    
    # 测试用例
    test_cases = [
        {
            "name": "基本聊天测试",
            "payload": {
                "question": "你好，我想了解一下今天的天气",
                "user_id": "wang"
            },
            "expected_fields": ["response", "react_agent_meta", "timestamp"]
        },
        {
            "name": "SQL查询测试",
            "payload": {
                "question": "请查询服务区的收入数据",
                "user_id": "test_user"
            },
            "expected_fields": ["response", "sql", "records", "react_agent_meta", "timestamp"]
        },
        {
            "name": "继续对话测试",
            "payload": {
                "question": "请详细说明一下",
                "user_id": "wang",
                "thread_id": None  # 将在第一个测试后设置
            },
            "expected_fields": ["response", "react_agent_meta", "timestamp"]
        }
    ]
    
    session = aiohttp.ClientSession()
    
    try:
        print("🧪 开始测试 API 设计文档合规性...")
        print("=" * 60)
        
        thread_id = None
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📋 测试 {i}: {test_case['name']}")
            print("-" * 40)
            
            # 如果是继续对话测试，使用之前的 thread_id
            if test_case["name"] == "继续对话测试" and thread_id:
                test_case["payload"]["thread_id"] = thread_id
            
            # 发送请求
            async with session.post(
                f"{base_url}/api/chat",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"}
            ) as response:
                
                print(f"📊 HTTP状态码: {response.status}")
                
                if response.status != 200:
                    print(f"❌ 请求失败，状态码: {response.status}")
                    continue
                
                # 解析响应
                result = await response.json()
                
                # 验证顶级结构
                required_top_fields = ["code", "message", "success", "data"]
                for field in required_top_fields:
                    if field not in result:
                        print(f"❌ 缺少顶级字段: {field}")
                    else:
                        print(f"✅ 顶级字段 {field}: {result[field]}")
                
                # 验证 data 字段结构
                if "data" in result:
                    data = result["data"]
                    print(f"\n📦 data 字段包含: {list(data.keys())}")
                    
                    # 验证必需字段
                    required_fields = ["response", "react_agent_meta", "timestamp"]
                    for field in required_fields:
                        if field not in data:
                            print(f"❌ data 中缺少必需字段: {field}")
                        else:
                            print(f"✅ 必需字段 {field}: 存在")
                    
                    # 验证可选字段
                    optional_fields = ["sql", "records"]
                    for field in optional_fields:
                        if field in data:
                            print(f"✅ 可选字段 {field}: 存在")
                        else:
                            print(f"ℹ️  可选字段 {field}: 不存在（正常）")
                    
                    # 验证 react_agent_meta 结构
                    if "react_agent_meta" in data:
                        meta = data["react_agent_meta"]
                        print(f"\n🔧 react_agent_meta 字段: {list(meta.keys())}")
                        
                        # 保存 thread_id 用于后续测试
                        if "thread_id" in meta:
                            thread_id = meta["thread_id"]
                            print(f"🆔 Thread ID: {thread_id}")
                    
                    # 验证 records 结构（如果存在）
                    if "records" in data:
                        records = data["records"]
                        print(f"\n📊 records 字段: {list(records.keys())}")
                        required_record_fields = ["columns", "rows", "total_row_count", "is_limited"]
                        for field in required_record_fields:
                            if field not in records:
                                print(f"❌ records 中缺少字段: {field}")
                            else:
                                print(f"✅ records 字段 {field}: 存在")
                
                print(f"\n✅ 测试 {i} 完成")
        
        print("\n" + "=" * 60)
        print("🎉 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await session.close()

async def test_error_handling():
    """测试错误处理"""
    
    base_url = "http://localhost:8000"
    session = aiohttp.ClientSession()
    
    try:
        print("\n🧪 测试错误处理...")
        print("=" * 60)
        
        # 测试参数错误
        test_cases = [
            {
                "name": "缺少问题",
                "payload": {"user_id": "test"},
                "expected_code": 400
            },
            {
                "name": "空问题",
                "payload": {"question": "", "user_id": "test"},
                "expected_code": 400
            },
            {
                "name": "问题过长",
                "payload": {"question": "x" * 2001, "user_id": "test"},
                "expected_code": 400
            }
        ]
        
        for test_case in test_cases:
            print(f"\n📋 错误测试: {test_case['name']}")
            
            async with session.post(
                f"{base_url}/api/chat",
                json=test_case["payload"],
                headers={"Content-Type": "application/json"}
            ) as response:
                
                result = await response.json()
                
                print(f"📊 HTTP状态码: {response.status}")
                print(f"📋 响应代码: {result.get('code')}")
                print(f"🎯 成功状态: {result.get('success')}")
                print(f"❌ 错误信息: {result.get('error')}")
                
                if response.status == test_case["expected_code"]:
                    print("✅ 错误处理正确")
                else:
                    print(f"❌ 期望状态码 {test_case['expected_code']}, 实际 {response.status}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    print("🚀 启动 API 设计文档合规性测试")
    print("请确保 API 服务已启动 (python api.py)")
    print("=" * 60)
    
    asyncio.run(test_api_design_compliance())
    asyncio.run(test_error_handling()) 