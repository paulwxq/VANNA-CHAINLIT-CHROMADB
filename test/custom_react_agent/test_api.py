#!/usr/bin/env python3
"""
Custom React Agent API 测试脚本

测试基本的API功能，包括：
1. 健康检查
2. 普通问答
3. SQL查询
4. 错误处理

运行前请确保API服务已启动：
python api.py
"""
import asyncio
import aiohttp
import json
import sys
from typing import Dict, Any

API_BASE_URL = "http://localhost:8000"

class APITester:
    """API测试类"""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_health_check(self) -> bool:
        """测试健康检查"""
        print("🔍 测试健康检查...")
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   ✅ 健康检查通过: {data}")
                    return True
                else:
                    print(f"   ❌ 健康检查失败: HTTP {response.status}")
                    return False
        except Exception as e:
            print(f"   ❌ 健康检查异常: {e}")
            return False
    
    async def test_chat_api(self, question: str, user_id: str = "test_user", 
                           thread_id: str = None) -> Dict[str, Any]:
        """测试聊天API"""
        print(f"\n💬 测试问题: {question}")
        
        payload = {
            "question": question,
            "user_id": user_id
        }
        if thread_id:
            payload["thread_id"] = thread_id
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                response_data = await response.json()
                
                print(f"   📊 HTTP状态: {response.status}")
                print(f"   📋 响应代码: {response_data.get('code')}")
                print(f"   🎯 成功状态: {response_data.get('success')}")
                
                if response_data.get('success'):
                    data = response_data.get('data', {})
                    print(f"   💡 回答: {data.get('response', '')[:100]}...")
                    
                    if 'sql' in data:
                        print(f"   🗄️  SQL: {data['sql'][:100]}...")
                    
                    if 'records' in data:
                        records = data['records']
                        print(f"   📈 数据行数: {records.get('total_row_count', 0)}")
                    
                    meta = data.get('react_agent_meta', {})
                    print(f"   🔧 使用工具: {meta.get('tools_used', [])}")
                    print(f"   🆔 会话ID: {meta.get('thread_id', '')}")
                    
                    return response_data
                else:
                    error = response_data.get('error', '未知错误')
                    print(f"   ❌ 请求失败: {error}")
                    return response_data
                    
        except Exception as e:
            print(f"   ❌ 请求异常: {e}")
            return {"success": False, "error": str(e)}
    
    async def run_test_suite(self):
        """运行完整的测试套件"""
        print("🚀 开始API测试套件")
        print("=" * 50)
        
        # 1. 健康检查
        health_ok = await self.test_health_check()
        if not health_ok:
            print("❌ 健康检查失败，停止测试")
            return
        
        # 2. 普通问答测试
        await self.test_chat_api("你好，你是谁？")
        
        # 3. SQL查询测试（假设有相关数据）
        result1 = await self.test_chat_api("请查询服务区的收入情况")
        
        # 4. 上下文对话测试
        thread_id = None
        if result1.get('success'):
            thread_id = result1.get('data', {}).get('react_agent_meta', {}).get('thread_id')
        
        if thread_id:
            await self.test_chat_api("请详细解释一下", thread_id=thread_id)
        
        # 5. 错误处理测试
        await self.test_chat_api("")  # 空问题
        await self.test_chat_api("a" * 3000)  # 超长问题
        
        print("\n" + "=" * 50)
        print("✅ 测试套件完成")

async def main():
    """主函数"""
    print("Custom React Agent API 测试工具")
    print("请确保API服务已在 http://localhost:8000 启动")
    print()
    
    # 检查是否要运行特定测试
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        async with APITester() as tester:
            await tester.test_chat_api(question)
    else:
        # 运行完整测试套件
        async with APITester() as tester:
            await tester.run_test_suite()

if __name__ == "__main__":
    asyncio.run(main()) 