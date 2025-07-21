"""
SQL验证器命令行入口
用于验证Question-SQL对中的SQL语句是否有效
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

from .sql_validation_agent import SQLValidationAgent
from data_pipeline.utils.logger import setup_logging


def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='SQL Validator - 验证Question-SQL对中的SQL语句',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本使用（仅验证，不修改文件）
  python -m data_pipeline.validators.sql_validate_cli --db-connection "postgresql://user:pass@localhost:5432/dbname" --input-file ./data.json
  
  # 使用task_id自动查找文件
  python -m data_pipeline.validators.sql_validate_cli --task-id manual_20250720_130541 --db-connection "postgresql://user:pass@localhost:5432/dbname"
  
  # 启用文件修改，但禁用LLM修复（仅删除无效SQL）
  python -m data_pipeline.validators.sql_validate_cli --db-connection "postgresql://user:pass@localhost:5432/dbname" --input-file ./data.json --modify-original-file --disable-llm-repair
  
  # 启用文件修改和LLM修复功能
  python -m data_pipeline.validators.sql_validate_cli --db-connection "postgresql://user:pass@localhost:5432/dbname" --input-file ./data.json --modify-original-file
  
  # 指定输出目录
  python -m data_pipeline.validators.sql_validate_cli --db-connection "postgresql://user:pass@localhost:5432/dbname" --input-file ./data.json --output-dir ./reports
  
  # 启用详细日志
  python -m data_pipeline.validators.sql_validate_cli --db-connection "postgresql://user:pass@localhost:5432/dbname" --input-file ./data.json --verbose
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--db-connection',
        required=True,
        help='数据库连接字符串 (postgresql://user:pass@host:port/dbname)'
    )
    
    # 可选参数（当使用task-id时，input-file变为可选）
    parser.add_argument(
        '--task-id',
        help='任务ID，指定后将自动在任务目录中查找Question-SQL文件'
    )
    
    parser.add_argument(
        '--input-file',
        help='输入的JSON文件路径（包含Question-SQL对）'
    )
    
    # 可选参数
    parser.add_argument(
        '--output-dir',
        help='验证报告输出目录（默认为输入文件同目录）'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        help='最大并发验证数（覆盖配置文件设置）'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        help='批处理大小（覆盖配置文件设置）'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        help='单个SQL验证超时时间（秒）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细日志输出'
    )
    
    parser.add_argument(
        '--log-file',
        help='日志文件路径'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅读取和解析文件，不执行验证'
    )
    
    parser.add_argument(
        '--save-json',
        action='store_true',
        help='同时保存详细的JSON报告'
    )
    
    parser.add_argument(
        '--disable-llm-repair',
        action='store_true',
        help='禁用LLM自动修复功能'
    )
    
    # 向后兼容的别名参数
    parser.add_argument(
        '--enable-llm-repair',
        action='store_true',
        help='启用LLM自动修复功能（与--disable-llm-repair相反，保持向后兼容性）'
    )
    
    parser.add_argument(
        '--no-modify-file',
        action='store_true',
        help='不修改原始JSON文件（仅生成验证报告）'
    )
    
    # 向后兼容的别名参数
    parser.add_argument(
        '--modify-original-file',
        action='store_true',
        help='修改原始JSON文件（与--no-modify-file相反，保持向后兼容性）'
    )
    
    return parser


def apply_config_overrides(args):
    """应用命令行参数覆盖配置"""
    from data_pipeline.config import SCHEMA_TOOLS_CONFIG
    
    sql_config = SCHEMA_TOOLS_CONFIG['sql_validation']
    
    if args.max_concurrent:
        sql_config['max_concurrent_validations'] = args.max_concurrent
        print(f"覆盖并发数配置: {args.max_concurrent}")
    
    if args.batch_size:
        sql_config['batch_size'] = args.batch_size
        print(f"覆盖批处理大小: {args.batch_size}")
    
    if args.timeout:
        sql_config['validation_timeout'] = args.timeout
        print(f"覆盖超时配置: {args.timeout}秒")
    
    if args.save_json:
        sql_config['save_detailed_json_report'] = True
        print(f"启用详细JSON报告保存")
    
    # 注意：现在是disable_llm_repair，逻辑反转，同时支持向后兼容的enable_llm_repair
    if args.disable_llm_repair and args.enable_llm_repair:
        print("警告: --disable-llm-repair 和 --enable-llm-repair 不能同时使用，优先使用 --disable-llm-repair")
        sql_config['enable_sql_repair'] = False
        print(f"LLM修复功能已禁用")
    elif args.disable_llm_repair:
        sql_config['enable_sql_repair'] = False
        print(f"LLM修复功能已禁用")
    elif args.enable_llm_repair:
        sql_config['enable_sql_repair'] = True
        print(f"启用LLM自动修复功能（向后兼容参数）")
    else:
        # 默认启用LLM修复功能
        sql_config['enable_sql_repair'] = True
        print(f"启用LLM自动修复功能（默认行为）")
    
    # 注意：现在是no_modify_file，逻辑反转，同时支持向后兼容的modify_original_file
    if args.no_modify_file and args.modify_original_file:
        print("警告: --no-modify-file 和 --modify-original-file 不能同时使用，优先使用 --no-modify-file")
        sql_config['modify_original_file'] = False
        print(f"不修改原文件")
    elif args.no_modify_file:
        sql_config['modify_original_file'] = False
        print(f"不修改原文件")
    elif args.modify_original_file:
        sql_config['modify_original_file'] = True
        print(f"启用原文件修改功能（向后兼容参数）")
    else:
        # 默认启用文件修改功能
        sql_config['modify_original_file'] = True
        print(f"启用原文件修改功能（默认行为）")


async def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 验证参数
    if not args.input_file and not args.task_id:
        print("错误: 必须指定 --input-file 或 --task-id 参数")
        parser.print_help()
        sys.exit(1)
    
    # 解析输入文件和输出目录
    input_file, output_dir = resolve_input_file_and_output_dir(args)
    
    if not input_file:
        if args.task_id:
            print(f"错误: 在任务目录中未找到Question-SQL文件 (*_pair.json)")
            print(f"任务ID: {args.task_id}")
        else:
            print(f"错误: 输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    input_path = Path(input_file)
    if not input_path.suffix.lower() == '.json':
        print(f"警告: 输入文件可能不是JSON格式: {input_file}")
    
    # 应用配置覆盖
    apply_config_overrides(args)
    
    try:
        # 创建SQL验证Agent
        agent = SQLValidationAgent(
            db_connection=args.db_connection,
            input_file=input_file,
            output_dir=output_dir,
            task_id=args.task_id  # 传递task_id
        )
        
        # 显示运行信息
        print(f"🚀 开始SQL验证...")
        print(f"📁 输入文件: {input_file}")
        if output_dir:
            print(f"📁 输出目录: {output_dir}")
        print(f"🔗 数据库: {_mask_db_connection(args.db_connection)}")
        
        if args.dry_run:
            print("\n🔍 执行预检查模式...")
            # 仅读取和验证文件格式
            questions_sqls = await agent._load_questions_sqls()
            print(f"✅ 成功读取 {len(questions_sqls)} 个Question-SQL对")
            print("📊 SQL样例:")
            for i, qs in enumerate(questions_sqls[:3], 1):
                print(f"  {i}. {qs['question']}")
                print(f"     SQL: {qs['sql'][:100]}{'...' if len(qs['sql']) > 100 else ''}")
                print()
            sys.exit(0)
        
        # 执行验证
        report = await agent.validate()
        
        # 输出结果
        success_rate = report['summary']['success_rate']
        
        if success_rate >= 0.9:  # 90%以上成功率
            print(f"\n🎉 验证完成，成功率: {success_rate:.1%}")
            exit_code = 0
        elif success_rate >= 0.7:  # 70%-90%成功率
            print(f"\n⚠️  验证完成，成功率较低: {success_rate:.1%}")
            exit_code = 1
        else:  # 70%以下成功率
            print(f"\n❌ 验证完成，成功率过低: {success_rate:.1%}")
            exit_code = 2
        
        print(f"📊 详细结果: {report['summary']['valid_sqls']}/{report['summary']['total_questions']} SQL有效")
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断，程序退出")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 程序执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _mask_db_connection(conn_str: str) -> str:
    """隐藏数据库连接字符串中的敏感信息"""
    import re
    return re.sub(r'://[^:]+:[^@]+@', '://***:***@', conn_str)


def resolve_input_file_and_output_dir(args):
    """解析输入文件和输出目录路径"""
    input_file = None
    output_dir = None
    
    if args.input_file:
        # 用户明确指定了输入文件
        input_file = args.input_file
        output_dir = args.output_dir or str(Path(input_file).parent)
    elif args.task_id:
        # 使用task_id自动查找输入文件
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        base_dir = SCHEMA_TOOLS_CONFIG.get("output_directory", "./data_pipeline/training_data/")
        
        # 处理相对路径
        from pathlib import Path
        if not Path(base_dir).is_absolute():
            # 相对于项目根目录解析
            project_root = Path(__file__).parent.parent.parent
            base_dir = project_root / base_dir
        
        task_dir = Path(base_dir) / args.task_id
        output_dir = args.output_dir or str(task_dir)
        
        # 在任务目录中查找Question-SQL文件
        if task_dir.exists():
            # 只搜索标准命名的文件，排除 _old 后缀
            possible_files = [
                f for f in task_dir.glob("*_pair.json") 
                if not f.name.endswith('_old') and '.backup' not in f.name
            ]
            if possible_files:
                # 选择最新的文件（按修改时间排序）
                input_file = str(max(possible_files, key=lambda f: f.stat().st_mtime))
            else:
                input_file = None
        else:
            input_file = None
    
    return input_file, output_dir


if __name__ == "__main__":
    asyncio.run(main()) 