# run_training.py
import os
import time
import re
import json
import sys
import requests
import pandas as pd
import argparse
from pathlib import Path
from sqlalchemy import create_engine


from .vanna_trainer import (
    train_ddl,
    train_documentation,
    train_sql_example,
    train_question_sql_pair,
    flush_training,
    shutdown_trainer
)

def check_embedding_model_connection():
    """检查嵌入模型连接是否可用    
    如果无法连接到嵌入模型，则终止程序执行    
    Returns:
        bool: 连接成功返回True，否则终止程序
    """
    from core.embedding_function import test_embedding_connection

    print("正在检查嵌入模型连接...")
    
    # 使用专门的测试函数进行连接测试
    test_result = test_embedding_connection()
    
    if test_result["success"]:
        print(f"可以继续训练过程。")
        return True
    else:
        print(f"\n错误: 无法连接到嵌入模型: {test_result['message']}")
        print("训练过程终止。请检查配置和API服务可用性。")
        sys.exit(1)

def read_file_by_delimiter(filepath, delimiter="---"):
    """通用读取：将文件按分隔符切片为多个段落"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = [block.strip() for block in content.split(delimiter) if block.strip()]
    return blocks

def read_markdown_file_by_sections(filepath):
    """专门用于Markdown文件：按标题(#、##、###)分割文档
    
    Args:
        filepath (str): Markdown文件路径
        
    Returns:
        list: 分割后的Markdown章节列表
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 确定文件是否为Markdown
    is_markdown = filepath.lower().endswith('.md') or filepath.lower().endswith('.markdown')
    
    if not is_markdown:
        # 非Markdown文件使用默认的---分隔
        return read_file_by_delimiter(filepath, "---")
    
    # 直接按照标题级别分割内容，处理#、##和###
    sections = []
    
    # 匹配所有级别的标题（#、##或###开头）
    header_pattern = r'(?:^|\n)((?:#|##|###)[^#].*?)(?=\n(?:#|##|###)[^#]|\Z)'
    all_sections = re.findall(header_pattern, content, re.DOTALL)
    
    for section in all_sections:
        section = section.strip()
        if section:
            sections.append(section)
    
    # 处理没有匹配到标题的情况
    if not sections and content.strip():
        sections = [content.strip()]
        
    return sections

def train_ddl_statements(ddl_file):
    """训练DDL语句
    Args:
        ddl_file (str): DDL文件路径
    """
    print(f"开始训练 DDL: {ddl_file}")
    if not os.path.exists(ddl_file):
        print(f"DDL 文件不存在: {ddl_file}")
        return
    for idx, ddl in enumerate(read_file_by_delimiter(ddl_file, ";"), start=1):
        try:
            print(f"\n DDL 训练 {idx}")
            train_ddl(ddl)
        except Exception as e:
            print(f"错误：DDL #{idx} - {e}")

def train_documentation_blocks(doc_file):
    """训练文档块
    Args:
        doc_file (str): 文档文件路径
    """
    print(f"开始训练 文档: {doc_file}")
    if not os.path.exists(doc_file):
        print(f"文档文件不存在: {doc_file}")
        return
    
    # 检查是否为Markdown文件
    is_markdown = doc_file.lower().endswith('.md') or doc_file.lower().endswith('.markdown')
    
    if is_markdown:
        # 使用Markdown专用分割器
        sections = read_markdown_file_by_sections(doc_file)
        print(f" Markdown文档已分割为 {len(sections)} 个章节")
        
        for idx, section in enumerate(sections, start=1):
            try:
                section_title = section.split('\n', 1)[0].strip()
                print(f"\n Markdown章节训练 {idx}: {section_title}")
                
                # 检查部分长度并提供警告
                if len(section) > 2000:
                    print(f" 章节 {idx} 长度为 {len(section)} 字符，接近API限制(2048)")
                
                train_documentation(section)
            except Exception as e:
                print(f" 错误：章节 #{idx} - {e}")
    else:
        # 非Markdown文件使用传统的---分隔
        for idx, doc in enumerate(read_file_by_delimiter(doc_file, "---"), start=1):
            try:
                print(f"\n 文档训练 {idx}")
                train_documentation(doc)
            except Exception as e:
                print(f" 错误：文档 #{idx} - {e}")

def train_sql_examples(sql_file):
    """训练SQL示例
    Args:
        sql_file (str): SQL示例文件路径
    """
    print(f" 开始训练 SQL 示例: {sql_file}")
    if not os.path.exists(sql_file):
        print(f" SQL 示例文件不存在: {sql_file}")
        return
    for idx, sql in enumerate(read_file_by_delimiter(sql_file, ";"), start=1):
        try:
            print(f"\n SQL 示例训练 {idx}")
            train_sql_example(sql)
        except Exception as e:
            print(f" 错误：SQL #{idx} - {e}")

def train_question_sql_pairs(qs_file):
    """训练问答对
    Args:
        qs_file (str): 问答对文件路径
    """
    print(f" 开始训练 问答对: {qs_file}")
    if not os.path.exists(qs_file):
        print(f" 问答文件不存在: {qs_file}")
        return
    try:
        with open(qs_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, start=1):
            if "::" not in line:
                continue
            question, sql = line.strip().split("::", 1)
            print(f"\n 问答训练 {idx}")
            train_question_sql_pair(question.strip(), sql.strip())
    except Exception as e:
        print(f" 错误：问答训练 - {e}")

def train_formatted_question_sql_pairs(formatted_file):
    """训练格式化的问答对文件
    支持两种格式：
    1. Question: xxx\nSQL: xxx (单行SQL)
    2. Question: xxx\nSQL:\nxxx\nxxx (多行SQL)
    
    Args:
        formatted_file (str): 格式化问答对文件路径
    """
    print(f" 开始训练 格式化问答对: {formatted_file}")
    if not os.path.exists(formatted_file):
        print(f" 格式化问答文件不存在: {formatted_file}")
        return
    
    # 读取整个文件内容
    with open(formatted_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 按双空行分割不同的问答对
    # 使用更精确的分隔符，避免误识别
    pairs = []
    # 使用大小写不敏感的正则表达式来分割
    import re
    blocks = re.split(r'\n\n(?=question\s*:)', content, flags=re.IGNORECASE)
    
    # 处理第一块（可能没有前导的"\n\nQuestion:"）
    first_block = blocks[0]
    if re.search(r'^\s*question\s*:', first_block.strip(), re.IGNORECASE):
        pairs.append(first_block.strip())
    elif re.search(r'question\s*:', first_block, re.IGNORECASE):
        # 处理文件开头没有Question:的情况
        question_match = re.search(r'question\s*:', first_block, re.IGNORECASE)
        pairs.append(first_block[question_match.start():].strip())
    
    # 处理其余块
    for block in blocks[1:]:
        pairs.append(block.strip())
    
    # 处理每个问答对
    successfully_processed = 0
    for idx, pair in enumerate(pairs, start=1):
        try:
            # 使用大小写不敏感的匹配
            question_match = re.search(r'question\s*:', pair, re.IGNORECASE)
            sql_match = re.search(r'sql\s*:', pair, re.IGNORECASE)
            
            if not question_match or not sql_match:
                print(f" 跳过不符合格式的对 #{idx}")
                continue
            
            # 确保SQL在Question之后
            if sql_match.start() <= question_match.end():
                print(f" SQL部分未找到，跳过对 #{idx}")
                continue
                
            # 提取问题部分
            question_start = question_match.end()
            sql_start = sql_match.start()
            
            question = pair[question_start:sql_start].strip()
            
            # 提取SQL部分（支持多行）
            sql_part = pair[sql_match.end():].strip()
            
            # 检查是否存在下一个Question标记（防止解析错误）
            next_question_match = re.search(r'question\s*:', pair[sql_match.end():], re.IGNORECASE)
            if next_question_match:
                sql_part = pair[sql_match.end():sql_match.end() + next_question_match.start()].strip()
            
            if not question or not sql_part:
                print(f" 问题或SQL为空，跳过对 #{idx}")
                continue
            
            # 训练问答对
            print(f"\n格式化问答训练 {idx}")
            print(f"问题: {question}")
            print(f"SQL: {sql_part}")
            train_question_sql_pair(question, sql_part)
            successfully_processed += 1
            
        except Exception as e:
            print(f" 错误：格式化问答训练对 #{idx} - {e}")
    
    print(f"格式化问答训练完成，共成功处理 {successfully_processed} 对问答（总计 {len(pairs)} 对）")

def train_json_question_sql_pairs(json_file):
    """训练JSON格式的问答对
    
    Args:
        json_file (str): JSON格式问答对文件路径
    """
    print(f" 开始训练 JSON格式问答对: {json_file}")
    if not os.path.exists(json_file):
        print(f" JSON问答文件不存在: {json_file}")
        return
    
    try:
        # 读取JSON文件
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 确保数据是列表格式
        if not isinstance(data, list):
            print(f" 错误: JSON文件格式不正确，应为问答对列表")
            return
            
        successfully_processed = 0
        for idx, pair in enumerate(data, start=1):
            try:
                # 检查问答对格式
                if not isinstance(pair, dict):
                    print(f" 跳过不符合格式的对 #{idx}")
                    continue
                
                # 大小写不敏感地查找question和sql键
                question_key = None
                sql_key = None
                question_value = None
                sql_value = None
                
                for key, value in pair.items():
                    if key.lower() == "question":
                        question_key = key
                        question_value = value
                    elif key.lower() == "sql":
                        sql_key = key
                        sql_value = value
                
                if question_key is None or sql_key is None:
                    print(f" 跳过不符合格式的对 #{idx}")
                    continue
                
                question = str(question_value).strip()
                sql = str(sql_value).strip()
                
                if not question or not sql:
                    print(f" 问题或SQL为空，跳过对 #{idx}")
                    continue
                
                # 训练问答对
                print(f"\n JSON格式问答训练 {idx}")
                print(f"问题: {question}")
                print(f"SQL: {sql}")
                train_question_sql_pair(question, sql)
                successfully_processed += 1
                
            except Exception as e:
                print(f" 错误：JSON问答训练对 #{idx} - {e}")
        
        print(f"JSON格式问答训练完成，共成功处理 {successfully_processed} 对问答（总计 {len(data)} 对）")
        
    except json.JSONDecodeError as e:
        print(f" 错误：JSON解析失败 - {e}")
    except Exception as e:
        print(f" 错误：处理JSON问答训练 - {e}")

def process_training_files(data_path, task_id=None, backup_vector_tables=False, truncate_vector_tables=False):
    """处理指定路径下的所有训练文件
    
    Args:
        data_path (str): 训练数据目录路径
        task_id (str): 任务ID，用于日志记录
        backup_vector_tables (bool): 是否备份vector表数据
        truncate_vector_tables (bool): 是否清空vector表数据
    """
    # 初始化日志
    if task_id:
        from data_pipeline.dp_logging import get_logger
        logger = get_logger("TrainingDataLoader", task_id)
        logger.info(f"扫描训练数据目录: {os.path.abspath(data_path)}")
    else:
        # 兼容原有调用方式
        print(f"\n===== 扫描训练数据目录: {os.path.abspath(data_path)} =====")
        logger = None
    
    # 检查目录是否存在
    if not os.path.exists(data_path):
        error_msg = f"错误: 训练数据目录不存在: {data_path}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return False
    
    # 日志输出辅助函数
    def log_message(message, level="info"):
        if logger:
            getattr(logger, level)(message)
        else:
            print(message)
    
    # Vector表管理（前置步骤）
    vector_stats = None
    if backup_vector_tables or truncate_vector_tables:
        # 参数验证和自动启用逻辑
        if truncate_vector_tables:
            backup_vector_tables = True
        
        try:
            import asyncio
            from data_pipeline.trainer.vector_table_manager import VectorTableManager
            
            log_message("🗂️ 开始执行Vector表管理...")
            
            vector_manager = VectorTableManager(data_path, task_id)
            vector_stats = asyncio.run(vector_manager.execute_vector_management(backup_vector_tables, truncate_vector_tables))
            
            log_message("✅ Vector表管理完成")
            
        except Exception as e:
            log_message(f"❌ Vector表管理失败: {e}", "error")
            return False
    
    # 初始化统计计数器
    stats = {
        "ddl": 0,
        "documentation": 0,
        "sql_example": 0,
        "question_sql_formatted": 0,
        "question_sql_json": 0
    }
    
    # 只扫描指定目录下的直接文件，不扫描子目录
    try:
        items = os.listdir(data_path)
        for item in items:
            item_path = os.path.join(data_path, item)
            
            # 只处理文件，跳过目录
            if not os.path.isfile(item_path):
                log_message(f"跳过子目录: {item}")
                continue
                
            file_lower = item.lower()
            
            # 根据文件类型调用相应的处理函数
            try:
                if file_lower.endswith(".ddl"):
                    log_message(f"处理DDL文件: {item_path}")
                    train_ddl_statements(item_path)
                    stats["ddl"] += 1
                    
                elif file_lower.endswith(".md") or file_lower.endswith(".markdown"):
                    log_message(f"处理文档文件: {item_path}")
                    train_documentation_blocks(item_path)
                    stats["documentation"] += 1
                    
                elif file_lower.endswith("_pair.json") or file_lower.endswith("_pairs.json"):
                    log_message(f"处理JSON问答对文件: {item_path}")
                    train_json_question_sql_pairs(item_path)
                    stats["question_sql_json"] += 1
                    
                elif file_lower.endswith("_pair.sql") or file_lower.endswith("_pairs.sql"):
                    log_message(f"处理格式化问答对文件: {item_path}")
                    train_formatted_question_sql_pairs(item_path)
                    stats["question_sql_formatted"] += 1
                    
                elif file_lower.endswith(".sql") and not (file_lower.endswith("_pair.sql") or file_lower.endswith("_pairs.sql")):
                    log_message(f"处理SQL示例文件: {item_path}")
                    train_sql_examples(item_path)
                    stats["sql_example"] += 1
                else:
                    log_message(f"跳过不支持的文件类型: {item}")
            except Exception as e:
                log_message(f"处理文件 {item_path} 时出错: {e}", "error")
                
    except OSError as e:
        log_message(f"读取目录失败: {e}", "error")
        return False
    
    # 打印处理统计
    log_message("训练文件处理统计:")
    log_message(f"DDL文件: {stats['ddl']}个")
    log_message(f"文档文件: {stats['documentation']}个")
    log_message(f"SQL示例文件: {stats['sql_example']}个")
    log_message(f"格式化问答对文件: {stats['question_sql_formatted']}个")
    log_message(f"JSON问答对文件: {stats['question_sql_json']}个")
    
    total_files = sum(stats.values())
    if total_files == 0:
        log_message(f"警告: 在目录 {data_path} 中未找到任何可训练的文件", "warning")
        return False, vector_stats
        
    return True, vector_stats

def check_pgvector_connection():
    """检查 PgVector 数据库连接是否可用
    
    Returns:
        bool: 连接成功返回True，否则返回False
    """
    import app_config
    from sqlalchemy import create_engine, text
    
    try:
        # 构建连接字符串
        pg_config = app_config.PGVECTOR_CONFIG
        connection_string = f"postgresql://{pg_config['user']}:{pg_config['password']}@{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
        
        print(f"正在测试 PgVector 数据库连接...")
        print(f"连接地址: {pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}")
        
        # 创建数据库引擎并测试连接
        engine = create_engine(connection_string)
        
        with engine.connect() as connection:
            # 测试基本连接
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
            
            # 检查是否安装了 pgvector 扩展
            try:
                result = connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
                extension_exists = result.fetchone() is not None
                
                if extension_exists:
                    print("✓ PgVector 扩展已安装")
                else:
                    print("⚠ 警告: PgVector 扩展未安装，请确保已安装 pgvector 扩展")
                    
            except Exception as ext_e:
                print(f"⚠ 无法检查 pgvector 扩展状态: {ext_e}")
            
            # 检查训练数据表是否存在
            try:
                result = connection.execute(text("SELECT tablename FROM pg_tables WHERE tablename = 'langchain_pg_embedding'"))
                table_exists = result.fetchone() is not None
                
                if table_exists:
                    # 获取表中的记录数
                    result = connection.execute(text("SELECT COUNT(*) FROM langchain_pg_embedding"))
                    count = result.fetchone()[0]
                    print(f"✓ 训练数据表存在，当前包含 {count} 条记录")
                else:
                    print("ℹ 训练数据表尚未创建（首次训练时会自动创建）")
                    
            except Exception as table_e:
                print(f"⚠ 无法检查训练数据表状态: {table_e}")
        
        print("✓ PgVector 数据库连接测试成功")
        return True
        
    except Exception as e:
        print(f"✗ PgVector 数据库连接失败: {e}")
        return False

def main():
    """主函数：配置和运行训练流程"""
    
    # 先导入所需模块
    import os
    import app_config
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='训练Vanna NL2SQL模型')
    
    # 获取默认路径并进行智能处理
    def resolve_training_data_path():
        """智能解析训练数据路径"""
        # 使用data_pipeline统一配置
        try:
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            config_path = SCHEMA_TOOLS_CONFIG.get("output_directory", './data_pipeline/training_data/')
        except ImportError:
            # 如果无法导入data_pipeline配置，使用默认路径
            config_path = './data_pipeline/training_data/'
        
        # 如果是绝对路径，直接返回
        if os.path.isabs(config_path):
            return config_path
        
        # 如果以 . 开头，相对于项目根目录解析
        if config_path.startswith('./') or config_path.startswith('../'):
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(project_root, config_path)
        
        # 其他情况，相对于项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(project_root, config_path)
    
    default_path = resolve_training_data_path()
    
    parser.add_argument('--data_path', type=str, default=default_path,
                        help='训练数据目录路径 (默认: 从data_pipeline.config.SCHEMA_TOOLS_CONFIG)')
    
    parser.add_argument('--backup-vector-tables', action='store_true',
                        help='备份vector表数据')
    
    parser.add_argument('--truncate-vector-tables', action='store_true',
                        help='清空vector表数据（自动启用备份）')
    
    args = parser.parse_args()
    
    # 使用Path对象处理路径以确保跨平台兼容性
    data_path = Path(args.data_path)
    
    # 显示路径解析结果
    print(f"\n===== 训练数据路径配置 =====")
    try:
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        config_value = SCHEMA_TOOLS_CONFIG.get("output_directory", "未配置")
        print(f"data_pipeline配置路径: {config_value}")
    except ImportError:
        print(f"data_pipeline配置: 无法导入")
    print(f"解析后的绝对路径: {os.path.abspath(data_path)}")
    print("==============================")
    
    # 设置正确的项目根目录路径
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 检查嵌入模型连接
    check_embedding_model_connection()
    
    # 根据配置的向量数据库类型显示相应信息
    vector_db_type = app_config.VECTOR_DB_TYPE.lower()
    
    if vector_db_type == "chromadb":
        # 打印ChromaDB相关信息
        try:
            try:
                import chromadb
                chroma_version = chromadb.__version__
            except ImportError:
                chroma_version = "未知"
            
            # 尝试查看当前使用的ChromaDB文件
            chroma_file = "chroma.sqlite3"  # 默认文件名
            
            # 使用项目根目录作为ChromaDB文件路径
            db_file_path = os.path.join(project_root, chroma_file)

            if os.path.exists(db_file_path):
                file_size = os.path.getsize(db_file_path) / 1024  # KB
                print(f"\n===== ChromaDB数据库: {os.path.abspath(db_file_path)} (大小: {file_size:.2f} KB) =====")
            else:
                print(f"\n===== 未找到ChromaDB数据库文件于: {os.path.abspath(db_file_path)} =====")
                
            # 打印ChromaDB版本
            print(f"===== ChromaDB客户端库版本: {chroma_version} =====\n")
        except Exception as e:
            print(f"\n===== 无法获取ChromaDB信息: {e} =====\n")
            
    elif vector_db_type == "pgvector":
        # 打印PgVector相关信息并测试连接
        print(f"\n===== PgVector数据库配置 =====")
        pg_config = app_config.PGVECTOR_CONFIG
        print(f"数据库地址: {pg_config['host']}:{pg_config['port']}")
        print(f"数据库名称: {pg_config['dbname']}")
        print(f"用户名: {pg_config['user']}")
        print("==============================\n")
        
        # 测试PgVector连接
        if not check_pgvector_connection():
            print("PgVector 数据库连接失败，训练过程终止。")
            sys.exit(1)
    else:
        print(f"\n===== 未知的向量数据库类型: {vector_db_type} =====\n")
    
    # 处理训练文件
    process_successful, vector_stats = process_training_files(data_path, None, 
                                                             args.backup_vector_tables, 
                                                             args.truncate_vector_tables)
    
    if process_successful:
        # 训练结束，刷新和关闭批处理器
        print("\n===== 训练完成，处理剩余批次 =====")
        flush_training()
        shutdown_trainer()
        
        # 验证数据是否成功写入
        print("\n===== 验证训练数据 =====")
        from core.vanna_llm_factory import create_vanna_instance
        vn = create_vanna_instance()
        
        # 根据向量数据库类型执行不同的验证逻辑
        try:
            training_data = vn.get_training_data()
            if training_data is not None and not training_data.empty:
                print(f"✓ 已从{vector_db_type.upper()}中检索到 {len(training_data)} 条训练数据进行验证。")
                
                # 显示训练数据类型统计
                if 'training_data_type' in training_data.columns:
                    type_counts = training_data['training_data_type'].value_counts()
                    print("训练数据类型统计:")
                    for data_type, count in type_counts.items():
                        print(f"  {data_type}: {count} 条")
                        
            elif training_data is not None and training_data.empty:
                print(f"⚠ 在{vector_db_type.upper()}中未找到任何训练数据。")
            else: # training_data is None
                print(f"⚠ 无法从Vanna获取训练数据 (可能返回了None)。请检查{vector_db_type.upper()}连接和Vanna实现。")

        except Exception as e:
            print(f"✗ 验证训练数据失败: {e}")
            print(f"请检查{vector_db_type.upper()}连接和表结构。")
    else:
        print("\n===== 未能找到或处理任何训练文件，训练过程终止 =====")
    
    # Vector表管理总结
    print("\n===== Vector表管理统计 =====")
    if vector_stats:
        if vector_stats.get("backup_performed", False):
            tables_info = vector_stats.get("tables_backed_up", {})
            print(f"✓ 备份执行: 成功备份 {len(tables_info)} 个表")
            for table_name, info in tables_info.items():
                if info.get("success", False):
                    print(f"  - {table_name}: {info['row_count']}行 -> {info['backup_file']} ({info['file_size']})")
                else:
                    print(f"  - {table_name}: 备份失败 - {info.get('error', '未知错误')}")
        else:
            print("- 备份执行: 未执行")
            
        if vector_stats.get("truncate_performed", False):
            truncate_info = vector_stats.get("truncate_results", {})
            print("✓ 清空执行: langchain_pg_embedding表已清空")
            for table_name, info in truncate_info.items():
                if info.get("success", False):
                    print(f"  - {table_name}: {info['rows_before']}行 -> 0行")
                else:
                    print(f"  - {table_name}: 清空失败 - {info.get('error', '未知错误')}")
        else:
            print("- 清空执行: 未执行")
            
        print(f"✓ 总耗时: {vector_stats.get('duration', 0):.1f}秒")
        
        if vector_stats.get("errors"):
            print(f"⚠ 错误: {'; '.join(vector_stats['errors'])}")
    else:
        print("- 未执行vector表管理操作")
    print("===========================")
    
    # 输出embedding模型信息
    print("\n===== Embedding模型信息 =====")
    try:
        from common.utils import get_current_embedding_config, get_current_model_info
        
        embedding_config = get_current_embedding_config()
        model_info = get_current_model_info()
        
        print(f"模型类型: {model_info['embedding_type']}")
        print(f"模型名称: {model_info['embedding_model']}")
        print(f"向量维度: {embedding_config.get('embedding_dimension', '未知')}")
        if 'base_url' in embedding_config:
            print(f"API服务: {embedding_config['base_url']}")
    except ImportError as e:
        print(f"警告: 无法导入配置工具函数: {e}")
        # 回退到旧的配置访问方式
        embedding_config = getattr(app_config, 'API_EMBEDDING_CONFIG', {})
        print(f"模型名称: {embedding_config.get('model_name', '未知')}")
        print(f"向量维度: {embedding_config.get('embedding_dimension', '未知')}")
        print(f"API服务: {embedding_config.get('base_url', '未知')}")
    
    # 根据配置显示向量数据库信息
    if vector_db_type == "chromadb":
        chroma_display_path = os.path.abspath(project_root)
        print(f"向量数据库: ChromaDB ({chroma_display_path})")
    elif vector_db_type == "pgvector":
        pg_config = app_config.PGVECTOR_CONFIG
        print(f"向量数据库: PgVector ({pg_config['host']}:{pg_config['port']}/{pg_config['dbname']})")
    
    print("===== 训练流程完成 =====\n")

if __name__ == "__main__":
    main() 