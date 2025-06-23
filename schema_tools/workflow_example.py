"""
Schema工作流编排器使用示例
演示如何使用SchemaWorkflowOrchestrator执行完整的工作流程
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_tools.schema_workflow_orchestrator import SchemaWorkflowOrchestrator
from schema_tools.utils.logger import setup_logging


async def example_complete_workflow():
    """完整工作流程示例"""
    print("=" * 60)
    print("完整工作流程示例")
    print("=" * 60)
    
    # 设置日志
    setup_logging(verbose=True)
    
    # 配置参数
    db_connection = "postgresql://user:password@localhost:5432/test_db"
    table_list_file = "schema_tools/tables.txt"
    business_context = "高速公路服务区管理系统"
    db_name = "highway_db"
    output_dir = "./example_output"
    
    try:
        # 创建工作流编排器
        orchestrator = SchemaWorkflowOrchestrator(
            db_connection=db_connection,
            table_list_file=table_list_file,
            business_context=business_context,
            db_name=db_name,
            output_dir=output_dir,
            enable_sql_validation=True,
            enable_llm_repair=True,
            modify_original_file=True
        )
        
        print(f"🚀 开始执行完整工作流程...")
        print(f"📁 输出目录: {output_dir}")
        print(f"🏢 业务背景: {business_context}")
        print(f"💾 数据库: {db_name}")
        
        # 执行完整工作流程
        report = await orchestrator.execute_complete_workflow()
        
        # 打印详细摘要
        orchestrator.print_final_summary(report)
        
        # 分析结果
        if report["success"]:
            print(f"\n🎉 工作流程执行成功!")
            
            # 显示各步骤详情
            results = report["processing_results"]
            
            if "ddl_md_generation" in results:
                ddl_md = results["ddl_md_generation"]
                print(f"📋 步骤1 - DDL/MD生成:")
                print(f"   处理表数: {ddl_md.get('processed_successfully', 0)}")
                print(f"   生成文件: {ddl_md.get('files_generated', 0)}")
                print(f"   耗时: {ddl_md.get('duration', 0):.2f}秒")
            
            if "question_sql_generation" in results:
                qs = results["question_sql_generation"]
                print(f"🤖 步骤2 - Question-SQL生成:")
                print(f"   生成主题: {qs.get('total_themes', 0)}")
                print(f"   成功主题: {qs.get('successful_themes', 0)}")
                print(f"   问答对数: {qs.get('total_questions', 0)}")
                print(f"   耗时: {qs.get('duration', 0):.2f}秒")
            
            if "sql_validation" in results:
                validation = results["sql_validation"]
                print(f"🔍 步骤3 - SQL验证:")
                print(f"   原始SQL数: {validation.get('original_sql_count', 0)}")
                print(f"   有效SQL数: {validation.get('valid_sql_count', 0)}")
                print(f"   成功率: {validation.get('success_rate', 0):.1%}")
                print(f"   耗时: {validation.get('duration', 0):.2f}秒")
            
            outputs = report["final_outputs"]
            print(f"\n📄 最终输出:")
            print(f"   主要文件: {outputs['primary_output_file']}")
            print(f"   问题总数: {outputs['final_question_count']}")
            
        else:
            print(f"\n❌ 工作流程执行失败:")
            error = report["error"]
            print(f"   失败步骤: {error['failed_step']}")
            print(f"   错误信息: {error['message']}")
            
            # 显示已完成的步骤
            completed = report["workflow_summary"]["completed_steps"]
            if completed:
                print(f"   已完成步骤: {', '.join(completed)}")
        
    except Exception as e:
        print(f"\n❌ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()


async def example_skip_validation():
    """跳过验证的工作流程示例"""
    print("=" * 60)
    print("跳过验证的工作流程示例")
    print("=" * 60)
    
    # 设置日志
    setup_logging(verbose=True)
    
    # 配置参数（跳过SQL验证）
    db_connection = "postgresql://user:password@localhost:5432/test_db"
    table_list_file = "schema_tools/tables.txt"
    business_context = "电商系统"
    db_name = "ecommerce_db"
    output_dir = "./example_output_no_validation"
    
    try:
        # 创建工作流编排器（跳过验证）
        orchestrator = SchemaWorkflowOrchestrator(
            db_connection=db_connection,
            table_list_file=table_list_file,
            business_context=business_context,
            db_name=db_name,
            output_dir=output_dir,
            enable_sql_validation=False,  # 跳过SQL验证
            enable_llm_repair=False,
            modify_original_file=False
        )
        
        print(f"🚀 开始执行工作流程（跳过验证）...")
        
        # 执行工作流程
        report = await orchestrator.execute_complete_workflow()
        
        # 打印摘要
        orchestrator.print_final_summary(report)
        
        print(f"\n📊 执行结果:")
        print(f"   成功: {'是' if report['success'] else '否'}")
        print(f"   完成步骤数: {len(report['workflow_summary']['completed_steps'])}")
        print(f"   总耗时: {report['workflow_summary']['total_duration']}秒")
        
    except Exception as e:
        print(f"\n❌ 示例执行失败: {e}")


async def example_error_handling():
    """错误处理示例"""
    print("=" * 60)
    print("错误处理示例")
    print("=" * 60)
    
    # 设置日志
    setup_logging(verbose=True)
    
    # 故意使用错误的配置来演示错误处理
    db_connection = "postgresql://invalid:invalid@localhost:5432/invalid_db"
    table_list_file = "nonexistent_tables.txt"
    business_context = "测试系统"
    db_name = "test_db"
    output_dir = "./example_error_output"
    
    try:
        # 创建工作流编排器
        orchestrator = SchemaWorkflowOrchestrator(
            db_connection=db_connection,
            table_list_file=table_list_file,
            business_context=business_context,
            db_name=db_name,
            output_dir=output_dir
        )
        
        print(f"🚀 开始执行工作流程（故意触发错误）...")
        
        # 执行工作流程
        report = await orchestrator.execute_complete_workflow()
        
        # 分析错误报告
        if not report["success"]:
            print(f"\n🔍 错误分析:")
            error = report["error"]
            print(f"   错误类型: {error['type']}")
            print(f"   错误信息: {error['message']}")
            print(f"   失败步骤: {error['failed_step']}")
            
            # 显示部分结果
            partial = report.get("partial_results", {})
            if partial:
                print(f"   部分结果: {list(partial.keys())}")
        
    except Exception as e:
        print(f"\n❌ 预期的错误: {e}")
        print("这是演示错误处理的正常情况")


def show_usage_examples():
    """显示使用示例"""
    print("=" * 60)
    print("SchemaWorkflowOrchestrator 使用示例")
    print("=" * 60)
    
    examples = [
        {
            "title": "1. 编程方式 - 完整工作流程",
            "code": """
import asyncio
from schema_tools.schema_workflow_orchestrator import SchemaWorkflowOrchestrator

async def run_complete_workflow():
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection="postgresql://user:pass@localhost:5432/dbname",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        db_name="highway_db",
        output_dir="./output"
    )
    
    # 一键执行完整流程
    report = await orchestrator.execute_complete_workflow()
    
    if report["success"]:
        print(f"✅ 编排完成！最终生成 {report['final_outputs']['final_question_count']} 个问答对")
        print(f"📄 输出文件: {report['final_outputs']['primary_output_file']}")
    else:
        print(f"❌ 编排失败: {report['error']['message']}")

asyncio.run(run_complete_workflow())
            """
        },
        {
            "title": "2. 命令行方式 - 完整工作流程",
            "code": """
python -m schema_tools.schema_workflow_orchestrator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --table-list tables.txt \\
  --business-context "高速公路服务区管理系统" \\
  --db-name highway_db \\
  --output-dir ./output
            """
        },
        {
            "title": "3. 命令行方式 - 跳过验证",
            "code": """
python -m schema_tools.schema_workflow_orchestrator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --table-list tables.txt \\
  --business-context "电商系统" \\
  --db-name ecommerce_db \\
  --skip-validation
            """
        },
        {
            "title": "4. 命令行方式 - 禁用LLM修复",
            "code": """
python -m schema_tools.schema_workflow_orchestrator \\
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \\
  --table-list tables.txt \\
  --business-context "管理系统" \\
  --db-name management_db \\
  --disable-llm-repair \\
  --verbose
            """
        }
    ]
    
    for example in examples:
        print(f"\n{example['title']}:")
        print(example['code'])


async def main():
    """主函数"""
    print("Schema工作流编排器使用示例")
    print("请选择要运行的示例:")
    print("1. 完整工作流程示例")
    print("2. 跳过验证的工作流程示例")
    print("3. 错误处理示例")
    print("4. 显示使用示例代码")
    print("0. 退出")
    
    try:
        choice = input("\n请输入选择 (0-4): ").strip()
        
        if choice == "1":
            await example_complete_workflow()
        elif choice == "2":
            await example_skip_validation()
        elif choice == "3":
            await example_error_handling()
        elif choice == "4":
            show_usage_examples()
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