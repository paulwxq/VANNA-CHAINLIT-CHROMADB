"""
Question-SQL生成器命令行入口
用于从已生成的DDL和MD文件生成Question-SQL训练数据
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

from .qs_agent import QuestionSQLGenerationAgent
from data_pipeline.utils.logger import setup_logging


def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='Question-SQL Generator - 从MD文件生成Question-SQL训练数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本使用
  python -m data_pipeline.qa_generation.qs_generator --output-dir ./output --table-list ./tables.txt --business-context "高速公路服务区管理系统"
  
  # 使用task_id自动解析路径
  python -m data_pipeline.qa_generation.qs_generator --task-id manual_20250720_130541 --table-list ./tables.txt --business-context "高速公路服务区管理系统"
  
  # 指定数据库名称
  python -m data_pipeline.qa_generation.qs_generator --output-dir ./output --table-list ./tables.txt --business-context "电商系统" --db-name ecommerce_db
  
  # 启用详细日志
  python -m data_pipeline.qa_generation.qs_generator --output-dir ./output --table-list ./tables.txt --business-context "管理系统" --verbose
        """
    )
    
    # 可选参数（当使用task-id时，output-dir变为可选）
    parser.add_argument(
        '--task-id',
        help='任务ID，指定后将自动构建输出目录路径 (基础目录/task_id)'
    )
    
    parser.add_argument(
        '--output-dir',
        help='包含DDL和MD文件的输出目录'
    )
    
    parser.add_argument(
        '--table-list',
        required=True,
        help='表清单文件路径（用于验证文件数量）'
    )
    
    parser.add_argument(
        '--business-context',
        required=True,
        help='业务上下文描述'
    )
    
    # 可选参数
    parser.add_argument(
        '--db-name',
        help='数据库名称（用于输出文件命名）'
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
    
    return parser

def resolve_output_directory(args):
    """解析输出目录路径"""
    if args.output_dir:
        # 用户明确指定了输出目录
        return args.output_dir
    elif args.task_id:
        # 使用task_id构建输出目录
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        base_dir = SCHEMA_TOOLS_CONFIG.get("output_directory", "./data_pipeline/training_data/")
        
        # 处理相对路径
        from pathlib import Path
        if not Path(base_dir).is_absolute():
            # 相对于项目根目录解析
            project_root = Path(__file__).parent.parent.parent
            base_dir = project_root / base_dir
        
        return str(Path(base_dir) / args.task_id)
    else:
        # 没有指定输出目录或task_id
        return None


async def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 解析输出目录
    output_dir = resolve_output_directory(args)
    
    # 验证参数
    if not output_dir:
        print("错误: 需要指定 --output-dir 或 --task-id 参数")
        parser.print_help()
        sys.exit(1)
    
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"错误: 输出目录不存在: {output_dir}")
        sys.exit(1)
    
    if not os.path.exists(args.table_list):
        print(f"错误: 表清单文件不存在: {args.table_list}")
        sys.exit(1)
    
    try:
        # 创建Agent
        agent = QuestionSQLGenerationAgent(
            output_dir=output_dir,
            table_list_file=args.table_list,
            business_context=args.business_context,
            db_name=args.db_name,
            task_id=args.task_id  # 传递task_id
        )
        
        # 执行生成
        print(f"🚀 开始生成Question-SQL训练数据...")
        print(f"📁 输出目录: {output_dir}")
        print(f"📋 表清单: {args.table_list}")
        print(f"🏢 业务背景: {args.business_context}")
        
        report = await agent.generate()
        
        # 输出结果
        if report['success']:
            if report['failed_themes']:
                print(f"\n⚠️  生成完成，但有 {len(report['failed_themes'])} 个主题失败")
                exit_code = 2  # 部分成功
            else:
                print("\n🎉 所有主题生成成功!")
                exit_code = 0  # 完全成功
        else:
            print("\n❌ 生成失败")
            exit_code = 1
        
        print(f"📁 输出文件: {report['output_file']}")
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


if __name__ == "__main__":
    asyncio.run(main()) 