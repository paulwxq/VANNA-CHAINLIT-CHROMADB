"""
Data Pipeline 命令行任务创建工具

专门用于手动创建任务，生成manual_前缀的task_id
仅创建任务目录，不涉及数据库或配置文件
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def generate_manual_task_id() -> str:
    """生成手动任务ID，格式: manual_YYYYMMDD_HHMMSS"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"manual_{timestamp}"


def resolve_base_directory():
    """解析基础输出目录"""
    try:
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        base_dir = SCHEMA_TOOLS_CONFIG.get("output_directory", "./data_pipeline/training_data/")
    except ImportError:
        # 如果无法导入配置，使用默认路径
        base_dir = "./data_pipeline/training_data/"
    
    # 处理相对路径
    if not Path(base_dir).is_absolute():
        # 相对于项目根目录解析
        project_root = Path(__file__).parent.parent
        base_dir = project_root / base_dir
    
    return Path(base_dir)


def create_task_directory(task_id: str, logger) -> Path:
    """创建任务目录"""
    base_dir = resolve_base_directory()
    task_dir = base_dir / task_id
    
    try:
        task_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"任务目录已创建: {task_dir}")
        return task_dir
    except Exception as e:
        logger.error(f"创建任务目录失败: {e}")
        raise


def extract_db_name_from_connection(connection_string: str) -> str:
    """从数据库连接字符串中提取数据库名称"""
    try:
        if '/' in connection_string:
            db_name = connection_string.split('/')[-1]
            if '?' in db_name:
                db_name = db_name.split('?')[0]
            return db_name if db_name else "database"
        else:
            return "database"
    except Exception:
        return "database"


def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='Data Pipeline 任务创建工具 - 创建手动执行的训练任务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本创建
  python -m data_pipeline.create_task_cli --business-context "电商系统" --db-connection "postgresql://user:pass@localhost:5432/ecommerce_db"
  
  # 指定表清单文件
  python -m data_pipeline.create_task_cli --table-list tables.txt --business-context "高速公路管理系统" --db-connection "postgresql://user:pass@localhost:5432/highway_db"
  
  # 指定任务名称
  python -m data_pipeline.create_task_cli --task-name "电商数据训练" --business-context "电商系统" --db-connection "postgresql://user:pass@localhost:5432/ecommerce_db"

创建成功后，可以使用返回的task_id进行分步执行：
  python -m data_pipeline.ddl_generation.ddl_md_generator --task-id <task_id> --db-connection "..." --table-list tables.txt --business-context "..."
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--business-context',
        required=True,
        help='业务上下文描述'
    )
    
    parser.add_argument(
        '--db-connection',
        required=True,
        help='数据库连接字符串 (postgresql://user:pass@host:port/dbname)'
    )
    
    # 可选参数
    parser.add_argument(
        '--table-list',
        help='表清单文件路径'
    )
    
    parser.add_argument(
        '--task-name',
        help='任务名称'
    )
    
    parser.add_argument(
        '--db-name',
        help='数据库名称（如果不提供，将从连接字符串中提取）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细输出和日志'
    )
    
    return parser


def print_usage_instructions(task_id: str, task_dir: Path, logger, **params):
    """输出使用说明"""
    # 总是向控制台输出结果，同时记录到日志
    output_lines = [
        "",
        "=" * 60,
        "🎉 任务创建成功！",
        "=" * 60,
        f"📋 任务ID: {task_id}",
        f"📁 任务目录: {task_dir}"
    ]
    
    if params.get('task_name'):
        output_lines.append(f"🎯 任务名称: {params['task_name']}")
    
    if params.get('db_name'):
        output_lines.append(f"🗄️  数据库: {params['db_name']}")
    
    output_lines.append(f"🏢 业务背景: {params['business_context']}")
    
    if params.get('table_list'):
        output_lines.append(f"📋 表清单文件: {params['table_list']}")
    
    output_lines.extend([
        "",
        "💡 现在可以使用以下命令执行分步操作：",
        "=" * 60
    ])
    
    # 构建示例命令
    db_conn = params['db_connection']
    business_context = params['business_context']
    table_list = params.get('table_list', 'tables.txt')
    
    command_lines = [
        "# 步骤1: 生成DDL和MD文件",
        f'python -m data_pipeline.ddl_generation.ddl_md_generator \\',
        f'  --task-id {task_id} \\',
        f'  --db-connection "{db_conn}" \\',
        f'  --table-list {table_list} \\',
        f'  --business-context "{business_context}"',
        "",
        "# 步骤2: 生成Question-SQL对",
        f'python -m data_pipeline.qa_generation.qs_generator \\',
        f'  --task-id {task_id} \\',
        f'  --table-list {table_list} \\',
        f'  --business-context "{business_context}"',
        "",
        "# 步骤3: 验证和修正SQL",
        f'python -m data_pipeline.validators.sql_validate_cli \\',
        f'  --task-id {task_id} \\',
        f'  --db-connection "{db_conn}"',
        "",
        "# 步骤4: 训练数据加载",
        f'python -m data_pipeline.trainer.run_training \\',
        f'  --task-id {task_id}',
        "",
        "=" * 60
    ]
    
    # 输出到控制台（总是显示）
    for line in output_lines + command_lines:
        print(line)
    
    # 记录到日志
    logger.info("任务创建成功总结:")
    for line in output_lines[2:]:  # 跳过装饰线
        if line and not line.startswith("="):
            logger.info(f"  {line}")
    
    logger.info("分步执行命令:")
    for line in command_lines:
        if line and not line.startswith("#") and line.strip():
            logger.info(f"  {line}")


def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 生成任务ID
    task_id = generate_manual_task_id()
    
    # 初始化统一日志服务
    try:
        from data_pipeline.dp_logging import get_logger
        logger = get_logger("CreateTaskCLI", task_id)
        logger.info(f"开始创建手动任务: {task_id}")
    except ImportError:
        # 如果无法导入统一日志服务，创建简单的logger
        import logging
        logger = logging.getLogger("CreateTaskCLI")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.warning("无法导入统一日志服务，使用简单日志")
    
    try:
        logger.info(f"生成任务ID: {task_id}")
        
        # 提取数据库名称
        db_name = args.db_name or extract_db_name_from_connection(args.db_connection)
        logger.info(f"数据库名称: {db_name}")
        
        # 验证表清单文件（如果提供）
        if args.table_list:
            if not os.path.exists(args.table_list):
                error_msg = f"表清单文件不存在: {args.table_list}"
                logger.error(error_msg)
                sys.exit(1)
            else:
                logger.info(f"表清单文件验证通过: {args.table_list}")
        
        # 创建任务目录
        task_dir = create_task_directory(task_id, logger)
        
        logger.info(f"任务创建完成: {task_id}")
        logger.info(f"参数信息: 业务背景='{args.business_context}', 数据库='{db_name}', 表清单='{args.table_list}'")
        
        # 输出使用说明
        print_usage_instructions(
            task_id=task_id,
            task_dir=task_dir,
            logger=logger,
            task_name=args.task_name,
            db_name=db_name,
            business_context=args.business_context,
            table_list=args.table_list,
            db_connection=args.db_connection
        )
        
        logger.info("任务创建工具执行完成")
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.warning("用户中断，程序退出")
        sys.exit(130)
    except Exception as e:
        logger.error(f"任务创建失败: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main() 