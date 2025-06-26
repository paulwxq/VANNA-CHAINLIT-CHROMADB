"""
DDL和MD文档生成器命令行入口
用于从PostgreSQL数据库生成DDL和MD训练数据
"""
import argparse
import asyncio
import sys
import os
import logging
from pathlib import Path

def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='DDL/MD文档生成器 - 从PostgreSQL数据库生成训练数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本使用
  python -m data_pipeline.ddl_md_generator --db-connection "postgresql://user:pass@host:5432/db" --table-list tables.txt --business-context "电商系统"
  
  # 指定输出目录
  python -m data_pipeline.ddl_md_generator --db-connection "..." --table-list tables.txt --business-context "电商系统" --output-dir ./data_pipeline/training_data/
  
  # 仅生成DDL文件
  python -m data_pipeline.ddl_md_generator --db-connection "..." --table-list tables.txt --business-context "电商系统" --pipeline ddl_only
  
  # 权限检查模式
  python -m data_pipeline.ddl_md_generator --db-connection "..." --check-permissions-only
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--db-connection',
        required=True,
        help='数据库连接字符串 (例如: postgresql://user:pass@localhost:5432/dbname)'
    )
    
    # 可选参数
    parser.add_argument(
        '--table-list',
        help='表清单文件路径'
    )
    
    parser.add_argument(
        '--business-context',
        help='业务上下文描述'
    )
    
    parser.add_argument(
        '--business-context-file',
        help='业务上下文文件路径'
    )
    
    parser.add_argument(
        '--output-dir',
        help='输出目录路径'
    )
    
    parser.add_argument(
        '--pipeline',
        choices=['full', 'ddl_only', 'analysis_only'],
        help='处理链类型'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        help='最大并发表数量'
    )
    
    # 功能开关
    parser.add_argument(
        '--no-filter-system-tables',
        action='store_true',
        help='禁用系统表过滤'
    )
    
    parser.add_argument(
        '--check-permissions-only',
        action='store_true',
        help='仅检查数据库权限，不处理表'
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

def load_config_with_overrides(args):
    """加载配置并应用命令行覆盖"""
    from data_pipeline.config import SCHEMA_TOOLS_CONFIG
    
    config = SCHEMA_TOOLS_CONFIG.copy()
    
    # 命令行参数覆盖配置
    if args.output_dir:
        config["output_directory"] = args.output_dir
    
    if args.pipeline:
        config["default_pipeline"] = args.pipeline
    
    if args.max_concurrent:
        config["max_concurrent_tables"] = args.max_concurrent
    
    if args.no_filter_system_tables:
        config["filter_system_tables"] = False
    
    if args.log_file:
        config["log_file"] = args.log_file
    
    return config

def load_business_context(args):
    """加载业务上下文"""
    if args.business_context_file:
        try:
            with open(args.business_context_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"警告: 无法读取业务上下文文件 {args.business_context_file}: {e}")
    
    if args.business_context:
        return args.business_context
    
    from data_pipeline.config import SCHEMA_TOOLS_CONFIG
    return SCHEMA_TOOLS_CONFIG.get("default_business_context", "数据库管理系统")

async def check_permissions_only(db_connection: str):
    """仅检查数据库权限"""
    from .training_data_agent import SchemaTrainingDataAgent
    
    print("🔍 检查数据库权限...")
    
    try:
        agent = SchemaTrainingDataAgent(
            db_connection=db_connection,
            table_list_file="",  # 不需要表清单
            business_context=""   # 不需要业务上下文
        )
        
        # 初始化Agent以建立数据库连接
        await agent._initialize()
        
        # 检查权限
        permissions = await agent.check_database_permissions()
        
        print("\n📋 权限检查结果:")
        print(f"  ✅ 数据库连接: {'可用' if permissions['connect'] else '不可用'}")
        print(f"  ✅ 元数据查询: {'可用' if permissions['select_metadata'] else '不可用'}")
        print(f"  ✅ 数据查询: {'可用' if permissions['select_data'] else '不可用'}")
        print(f"  ℹ️  数据库类型: {'只读' if permissions['is_readonly'] else '读写'}")
        
        # 修复判断逻辑：is_readonly=False表示可读写，是好事
        required_permissions = ['connect', 'select_metadata', 'select_data']
        has_required_permissions = all(permissions.get(perm, False) for perm in required_permissions)
        
        if has_required_permissions:
            print("\n✅ 数据库权限检查通过，可以开始处理")
            return True
        else:
            print("\n❌ 数据库权限不足，请检查配置")
            return False
            
    except Exception as e:
        print(f"\n❌ 权限检查失败: {e}")
        return False

async def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    from data_pipeline.utils.logger import setup_logging
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 仅权限检查模式
    if args.check_permissions_only:
        success = await check_permissions_only(args.db_connection)
        sys.exit(0 if success else 1)
    
    # 验证必需参数
    if not args.table_list:
        print("错误: 需要指定 --table-list 参数")
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(args.table_list):
        print(f"错误: 表清单文件不存在: {args.table_list}")
        sys.exit(1)
    
    try:
        # 加载配置和业务上下文
        config = load_config_with_overrides(args)
        business_context = load_business_context(args)
        
        # 创建Agent
        from .training_data_agent import SchemaTrainingDataAgent
        
        agent = SchemaTrainingDataAgent(
            db_connection=args.db_connection,
            table_list_file=args.table_list,
            business_context=business_context,
            output_dir=config["output_directory"],
            pipeline=config["default_pipeline"]
        )
        
        # 执行生成
        print("🚀 开始生成DDL和MD文档...")
        report = await agent.generate_training_data()
        
        # 输出结果
        if report['summary']['failed'] == 0:
            print("\n🎉 所有表处理成功!")
        else:
            print(f"\n⚠️  处理完成，但有 {report['summary']['failed']} 个表失败")
        
        print(f"📁 输出目录: {config['output_directory']}")
        
        # 如果有失败的表，返回非零退出码
        sys.exit(1 if report['summary']['failed'] > 0 else 0)
        
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