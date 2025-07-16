#!/usr/bin/env python3
"""
简化版 valid_sql 测试脚本
只测试三种错误场景：table不存在、column不存在、语法错误
"""
import asyncio
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入必要的模块
try:
    from agent import CustomReactAgent
    from sql_tools import valid_sql
    from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
except ImportError as e:
    logger.error(f"导入失败: {e}")
    logger.info("请确保在正确的目录下运行此脚本")
    exit(1)

class SimpleValidSqlTester:
    """简化版 valid_sql 测试类"""
    
    def __init__(self):
        self.agent = None
    
    async def setup(self):
        """初始化 Agent"""
        logger.info("🚀 初始化 CustomReactAgent...")
        try:
            self.agent = await CustomReactAgent.create()
            logger.info("✅ Agent 初始化完成")
        except Exception as e:
            logger.error(f"❌ Agent 初始化失败: {e}")
            raise
    
    async def cleanup(self):
        """清理资源"""
        if self.agent:
            await self.agent.close()
            logger.info("✅ Agent 资源已清理")
    
    def test_valid_sql_direct(self, sql: str) -> str:
        """直接测试 valid_sql 工具"""
        logger.info(f"🔧 直接测试 valid_sql 工具")
        logger.info(f"SQL: {sql}")
        
        result = valid_sql(sql)
        logger.info(f"结果: {result}")
        return result
    
    async def test_llm_response_to_error(self, question: str, error_sql: str, error_message: str):
        """测试 LLM 对验证错误的响应"""
        logger.info(f"🧠 测试 LLM 对验证错误的响应")
        logger.info(f"问题: {question}")
        logger.info(f"错误SQL: {error_sql}")
        logger.info(f"错误信息: {error_message}")
        
        # 创建模拟的 state
        state = {
            "thread_id": "test_thread",
            "messages": [
                HumanMessage(content=question),
                ToolMessage(
                    content=error_sql,
                    name="generate_sql",
                    tool_call_id="test_call_1"
                ),
                ToolMessage(
                    content=error_message,
                    name="valid_sql", 
                    tool_call_id="test_call_2"
                )
            ],
            "suggested_next_step": "analyze_validation_error"
        }
        
        try:
            # 调用 Agent 的内部方法来测试处理逻辑
            messages_for_llm = list(state["messages"])
            
            # 添加验证错误指导
            error_guidance = self.agent._generate_validation_error_guidance(error_message)
            messages_for_llm.append(SystemMessage(content=error_guidance))
            
            logger.info(f"📝 添加的错误指导: {error_guidance}")
            
            # 调用 LLM 看如何处理
            response = await self.agent.llm_with_tools.ainvoke(messages_for_llm)
            logger.info(f"🤖 LLM 响应: {response.content}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")
            return None

async def test_three_scenarios():
    """测试三种错误场景"""
    logger.info("🧪 测试三种 valid_sql 错误场景")
    
    # 三种测试用例
    test_cases = [
        # {
        #     "name": "表不存在",
        #     "question": "查询员工表的信息",
        #     "sql": "SELECT * FROM non_existent_table LIMIT 1"
        # },
        # {
        #     "name": "字段不存在", 
        #     "question": "查询每个服务区的经理姓名",
        #     "sql": "SELECT non_existent_field FROM bss_business_day_data LIMIT 1"
        # },
        {
            "name": "语法错误",
            "question": "查询服务区数据 WHERE",
            "sql": "SELECT service_name, pay_sum FROM bss_business_day_data WHERE service_name = '庐山服务区' AS service_alias"
        }
    ]
    
    tester = SimpleValidSqlTester()
    
    try:
        await tester.setup()
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"测试用例 {i}: {test_case['name']}")
            logger.info(f"{'='*50}")
            
            # 1. 直接测试 valid_sql
            direct_result = tester.test_valid_sql_direct(test_case["sql"])
            
            # 2. 测试 LLM 响应
            llm_response = await tester.test_llm_response_to_error(
                test_case["question"], 
                test_case["sql"], 
                direct_result
            )
            
            # 简单的结果分析
            logger.info(f"\n📊 结果分析:")
            if "失败" in direct_result:
                logger.info("✅ valid_sql 正确捕获错误")
            else:
                logger.warning("⚠️ valid_sql 可能未正确捕获错误")
            
            if llm_response and ("错误" in llm_response.content or "失败" in llm_response.content):
                logger.info("✅ LLM 正确处理验证错误")
            else:
                logger.warning("⚠️ LLM 可能未正确处理验证错误")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await tester.cleanup()

async def main():
    """主函数"""
    logger.info("🚀 简化版 valid_sql 测试")
    await test_three_scenarios()
    logger.info("\n✅ 测试完成")

if __name__ == "__main__":
    asyncio.run(main()) 