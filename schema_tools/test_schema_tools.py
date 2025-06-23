"""
测试Schema Tools模块
"""
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_basic_functionality():
    """测试基本功能"""
    print("===== 测试 Schema Tools =====")
    
    # 1. 测试配置
    from schema_tools.config import SCHEMA_TOOLS_CONFIG, validate_config
    print("\n1. 测试配置验证...")
    try:
        validate_config()
        print("✅ 配置验证通过")
    except Exception as e:
        print(f"❌ 配置验证失败: {e}")
        return
    
    # 2. 测试工具注册
    from schema_tools.tools import ToolRegistry
    print("\n2. 已注册的工具:")
    tools = ToolRegistry.list_tools()
    for tool in tools:
        print(f"  - {tool}")
    
    # 3. 创建测试表清单文件
    test_tables_file = "test_tables.txt"
    with open(test_tables_file, 'w', encoding='utf-8') as f:
        f.write("# 测试表清单\n")
        f.write("public.users\n")
        f.write("public.orders\n")
        f.write("hr.employees\n")
    print(f"\n3. 创建测试表清单文件: {test_tables_file}")
    
    # 4. 测试权限检查（仅模拟）
    print("\n4. 测试数据库权限检查...")
    
    # 这里需要真实的数据库连接字符串
    # 从环境变量或app_config获取
    try:
        import app_config
        if hasattr(app_config, 'PGVECTOR_CONFIG'):
            pg_config = app_config.PGVECTOR_CONFIG
            db_connection = f"postgresql://{pg_config['user']}:{pg_config['password']}@{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
            print(f"使用PgVector数据库配置")
        else:
            print("⚠️ 未找到数据库配置，跳过权限测试")
            db_connection = None
    except:
        print("⚠️ 无法导入app_config，跳过权限测试")
        db_connection = None
    
    if db_connection:
        from schema_tools.training_data_agent import SchemaTrainingDataAgent
        
        try:
            agent = SchemaTrainingDataAgent(
                db_connection=db_connection,
                table_list_file=test_tables_file,
                business_context="测试业务系统"
            )
            
            permissions = await agent.check_database_permissions()
            print(f"数据库权限: {permissions}")
        except Exception as e:
            print(f"❌ 权限检查失败: {e}")
    
    # 清理测试文件
    if os.path.exists(test_tables_file):
        os.remove(test_tables_file)
    
    print("\n===== 测试完成 =====")

async def test_table_parser():
    """测试表清单解析器"""
    print("\n===== 测试表清单解析器 =====")
    
    from schema_tools.utils.table_parser import TableListParser
    
    parser = TableListParser()
    
    # 测试字符串解析
    test_cases = [
        "public.users",
        "hr.employees,sales.orders",
        "users\norders\nproducts",
        "schema.table_name"
    ]
    
    for test_str in test_cases:
        result = parser.parse_string(test_str)
        print(f"输入: {repr(test_str)}")
        print(f"结果: {result}")
        print()

async def test_system_filter():
    """测试系统表过滤器"""
    print("\n===== 测试系统表过滤器 =====")
    
    from schema_tools.utils.system_filter import SystemTableFilter
    
    filter = SystemTableFilter()
    
    test_tables = [
        "pg_class",
        "information_schema.tables",
        "public.users",
        "hr.employees",
        "pg_temp_1.temp_table",
        "my_table"
    ]
    
    for table in test_tables:
        if '.' in table:
            schema, name = table.split('.', 1)
        else:
            schema, name = 'public', table
        
        is_system = filter.is_system_table(schema, name)
        print(f"{table}: {'系统表' if is_system else '用户表'}")

if __name__ == "__main__":
    print("Schema Tools 测试脚本\n")
    
    # 运行测试
    asyncio.run(test_basic_functionality())
    asyncio.run(test_table_parser())
    asyncio.run(test_system_filter())