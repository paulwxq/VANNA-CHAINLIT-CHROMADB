"""
SQL验证器使用示例
演示如何使用SQL验证功能
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_tools import SQLValidationAgent
from data_pipeline.utils.logger import setup_logging


async def example_basic_validation():
    """基本SQL验证示例"""
    print("=" * 60)
    print("基本SQL验证示例")
    print("=" * 60)
    
    # 创建测试数据
    test_data = [
        {
            "question": "查询所有用户",
            "sql": "SELECT * FROM users;"
        },
        {
            "question": "按年龄分组统计用户数",
            "sql": "SELECT age, COUNT(*) as user_count FROM users GROUP BY age ORDER BY age;"
        },
        {
            "question": "查询不存在的表",
            "sql": "SELECT * FROM non_existent_table;"
        },
        {
            "question": "语法错误的SQL",
            "sql": "SELECT * FORM users;"  # FORM而不是FROM
        }
    ]
    
    # 保存测试数据到文件
    test_file = Path("test_sql_data.json")
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)
    
    print(f"创建测试文件: {test_file}")
    print(f"包含 {len(test_data)} 个Question-SQL对")
    
    # 这里需要实际的数据库连接字符串
    # 请根据实际情况修改
    db_connection = "postgresql://user:password@localhost:5432/test_db"
    
    try:
        # 创建SQL验证Agent
        agent = SQLValidationAgent(
            db_connection=db_connection,
            input_file=str(test_file),
            output_dir="./validation_example_output"
        )
        
        print(f"\n开始验证...")
        
        # 执行验证
        report = await agent.validate()
        
        print(f"\n验证完成!")
        print(f"成功率: {report['summary']['success_rate']:.1%}")
        print(f"有效SQL: {report['summary']['valid_sqls']}/{report['summary']['total_questions']}")
        
        # 显示错误详情
        if report['errors']:
            print(f"\n错误详情:")
            for i, error in enumerate(report['errors'], 1):
                print(f"  {i}. {error['error']}")
                print(f"     SQL: {error['sql'][:100]}...")
        
    except Exception as e:
        print(f"验证失败: {e}")
        print("请检查数据库连接字符串和数据库权限")
    
    finally:
        # 清理测试文件
        if test_file.exists():
            test_file.unlink()
            print(f"\n清理测试文件: {test_file}")


async def example_with_real_data():
    """使用真实数据的SQL验证示例"""
    print("=" * 60)
    print("真实数据SQL验证示例")
    print("=" * 60)
    
    # 检查是否有现有的Question-SQL文件
    possible_files = list(Path(".").glob("qs_*_pair.json"))
    
    if not possible_files:
        print("未找到现有的Question-SQL文件")
        print("请先运行 qs_generator 生成Question-SQL对，或使用基本示例")
        return
    
    input_file = possible_files[0]
    print(f"找到文件: {input_file}")
    
    # 读取文件内容预览
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"文件包含 {len(data)} 个Question-SQL对")
    print(f"前3个问题预览:")
    for i, item in enumerate(data[:3], 1):
        print(f"  {i}. {item['question']}")
    
    # 数据库连接（需要根据实际情况修改）
    db_connection = "postgresql://user:password@localhost:5432/your_db"
    
    try:
        agent = SQLValidationAgent(
            db_connection=db_connection,
            input_file=str(input_file),
            output_dir="./validation_real_output"
        )
        
        print(f"\n开始验证...")
        report = await agent.validate()
        
        print(f"\n验证结果:")
        print(f"  总SQL数: {report['summary']['total_questions']}")
        print(f"  有效SQL: {report['summary']['valid_sqls']}")
        print(f"  无效SQL: {report['summary']['invalid_sqls']}")
        print(f"  成功率: {report['summary']['success_rate']:.1%}")
        print(f"  平均耗时: {report['summary']['average_execution_time']:.3f}秒")
        
    except Exception as e:
        print(f"验证失败: {e}")


async def example_configuration_demo():
    """配置演示示例"""
    print("=" * 60)
    print("配置选项演示")
    print("=" * 60)
    
    from data_pipeline.config import SCHEMA_TOOLS_CONFIG
    
    print("当前SQL验证配置:")
    sql_config = SCHEMA_TOOLS_CONFIG['sql_validation']
    for key, value in sql_config.items():
        print(f"  {key}: {value}")
    
    print("\n可以通过命令行参数覆盖配置:")
    print("  --max-concurrent 10    # 最大并发数")
    print("  --batch-size 20        # 批处理大小")
    print("  --timeout 60           # 验证超时时间")
    
    print("\n或者在代码中修改配置:")
    print("  SCHEMA_TOOLS_CONFIG['sql_validation']['max_concurrent_validations'] = 10")


def print_usage_examples():
    """打印使用示例"""
    print("=" * 60)
    print("SQL验证器命令行使用示例")
    print("=" * 60)
    
    examples = [
        {
            "title": "基本验证",
            "command": """python -m schema_tools.sql_validator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --input-file ./qs_data.json"""
        },
        {
            "title": "指定输出目录",
            "command": """python -m schema_tools.sql_validator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --input-file ./qs_data.json \\
  --output-dir ./reports"""
        },
        {
            "title": "调整性能参数",
            "command": """python -m schema_tools.sql_validator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --input-file ./qs_data.json \\
  --max-concurrent 10 \\
  --batch-size 20 \\
  --timeout 60"""
        },
        {
            "title": "预检查模式",
            "command": """python -m schema_tools.sql_validator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --input-file ./qs_data.json \\
  --dry-run"""
        },
        {
            "title": "详细日志",
            "command": """python -m schema_tools.sql_validator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --input-file ./qs_data.json \\
  --verbose \\
  --log-file validation.log"""
        }
    ]
    
    for example in examples:
        print(f"\n{example['title']}:")
        print(example['command'])


async def main():
    """主函数"""
    # 设置日志
    setup_logging(verbose=True)
    
    print("Schema Tools SQL验证器示例")
    print("请选择要运行的示例:")
    print("1. 基本SQL验证示例")
    print("2. 真实数据验证示例")
    print("3. 配置选项演示")
    print("4. 命令行使用示例")
    print("0. 退出")
    
    try:
        choice = input("\n请输入选择 (0-4): ").strip()
        
        if choice == "1":
            await example_basic_validation()
        elif choice == "2":
            await example_with_real_data()
        elif choice == "3":
            await example_configuration_demo()
        elif choice == "4":
            print_usage_examples()
        elif choice == "0":
            print("退出示例程序")
        else:
            print("无效选择")
    
    except KeyboardInterrupt:
        print("\n\n用户中断，退出程序")
    except Exception as e:
        print(f"\n示例执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 