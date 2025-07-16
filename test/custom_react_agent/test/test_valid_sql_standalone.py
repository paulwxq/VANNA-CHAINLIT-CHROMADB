#!/usr/bin/env python3
"""
独立测试 valid_sql 错误处理流程
不修改任何现有代码，只模拟测试场景
"""
import asyncio
import logging
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockValidSqlTool:
    """模拟 valid_sql 工具的行为"""
    
    @staticmethod
    def valid_sql(sql: str) -> str:
        """模拟 valid_sql 工具的验证逻辑"""
        logger.info(f"🔧 [Mock Tool] valid_sql - 待验证SQL: {sql}")
        
        # 模拟语法错误检测
        if "AS service_alias" in sql and "WHERE" in sql:
            logger.warning("   SQL验证失败：语法错误 - WHERE子句后不能直接使用AS别名")
            return "SQL验证失败：语法错误。详细错误：syntax error at or near \"AS\""
        
        # 模拟表不存在检测
        if "non_existent_table" in sql:
            logger.warning("   SQL验证失败：表不存在")
            return "SQL验证失败：表不存在。详细错误：relation \"non_existent_table\" does not exist"
        
        # 模拟字段不存在检测
        if "non_existent_field" in sql:
            logger.warning("   SQL验证失败：字段不存在")
            return "SQL验证失败：字段不存在。详细错误：column \"non_existent_field\" does not exist"
        
        logger.info("   ✅ SQL验证通过")
        return "SQL验证通过：语法正确且字段存在"

class MockLLM:
    """模拟 LLM 的响应行为"""
    
    @staticmethod
    async def respond_to_validation_error(question: str, error_sql: str, error_message: str) -> str:
        """模拟 LLM 对验证错误的响应"""
        logger.info(f"🧠 [Mock LLM] 处理验证错误")
        logger.info(f"问题: {question}")
        logger.info(f"错误SQL: {error_sql}")
        logger.info(f"错误信息: {error_message}")
        
        # 模拟不同类型的错误处理
        if "语法错误" in error_message:
            if "AS service_alias" in error_sql:
                response = """我发现了SQL语法错误。在WHERE子句后不能直接使用AS别名。

正确的SQL应该是：
```sql
SELECT service_name, pay_sum FROM bss_business_day_data WHERE service_name = '庐山服务区'
```

或者如果需要别名，应该这样写：
```sql
SELECT service_name AS service_alias, pay_sum FROM bss_business_day_data WHERE service_name = '庐山服务区'
```

问题在于AS别名应该在SELECT子句中定义，而不是在WHERE子句后。"""
        elif "表不存在" in error_message:
            response = """抱歉，您查询的表不存在。根据我的了解，系统中没有名为"non_existent_table"的表。

可用的表包括：
- bss_business_day_data (业务日数据表)
- bss_car_day_count (车辆日统计表)
- bss_company (公司信息表)

请确认您要查询的表名是否正确。"""
        elif "字段不存在" in error_message:
            response = """抱歉，您查询的字段不存在。根据我的了解，bss_business_day_data表中没有名为"non_existent_field"的字段。

该表的主要字段包括：
- service_name (服务区名称)
- pay_sum (支付金额)
- business_date (业务日期)

请确认您要查询的字段名是否正确。"""
        else:
            response = f"SQL验证失败：{error_message}。请检查SQL语句的语法和字段名称。"
        
        logger.info(f"🤖 [Mock LLM] 响应: {response[:100]}...")
        return response

class StandaloneValidSqlTester:
    """独立的 valid_sql 测试类"""
    
    def __init__(self):
        self.mock_valid_sql = MockValidSqlTool()
        self.mock_llm = MockLLM()
    
    def test_valid_sql_direct(self, sql: str) -> str:
        """直接测试 valid_sql 工具"""
        logger.info(f"🔧 直接测试 valid_sql 工具")
        logger.info(f"SQL: {sql}")
        
        result = self.mock_valid_sql.valid_sql(sql)
        logger.info(f"结果: {result}")
        return result
    
    async def test_llm_response_to_error(self, question: str, error_sql: str, error_message: str):
        """测试 LLM 对验证错误的响应"""
        logger.info(f"🧠 测试 LLM 对验证错误的响应")
        
        response = await self.mock_llm.respond_to_validation_error(question, error_sql, error_message)
        return response

async def test_three_scenarios():
    """测试三种错误场景"""
    logger.info("🧪 测试三种 valid_sql 错误场景")
    
    # 三种测试用例
    test_cases = [
        {
            "name": "表不存在",
            "question": "查询员工表的信息",
            "sql": "SELECT * FROM non_existent_table LIMIT 1"
        },
        {
            "name": "字段不存在", 
            "question": "查询每个服务区的经理姓名",
            "sql": "SELECT non_existent_field FROM bss_business_day_data LIMIT 1"
        },
        {
            "name": "语法错误",
            "question": "查询服务区数据 WHERE",
            "sql": "SELECT service_name, pay_sum FROM bss_business_day_data WHERE service_name = '庐山服务区' AS service_alias"
        }
    ]
    
    tester = StandaloneValidSqlTester()
    
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
        
        if llm_response and ("错误" in llm_response or "抱歉" in llm_response or "SQL" in llm_response):
            logger.info("✅ LLM 正确处理验证错误")
        else:
            logger.warning("⚠️ LLM 可能未正确处理验证错误")
        
        logger.info(f"\n📝 LLM 完整响应:")
        logger.info(llm_response)

async def main():
    """主函数"""
    logger.info("🚀 独立 valid_sql 测试")
    await test_three_scenarios()
    logger.info("\n✅ 测试完成")

if __name__ == "__main__":
    asyncio.run(main()) 