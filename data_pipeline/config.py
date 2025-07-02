import os
import sys

# 导入app_config获取数据库等配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import app_config
except ImportError:
    app_config = None

# Schema Tools专用配置
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "default_db_connection": None,  # 从命令行指定
    "default_business_context": "数据库管理系统", 
    "output_directory": "./data_pipeline/training_data/",
    
    # 处理链配置
    "default_pipeline": "full",
    "available_pipelines": {
        "full": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator", 
            "ddl_generator", 
            "doc_generator"
        ],
        "ddl_only": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator", 
            "ddl_generator"
        ],
        "analysis_only": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator"
        ]
    },
    
    # 数据处理配置
    "sample_data_limit": 20,                    # 用于LLM分析的采样数据量
    "enum_detection_sample_limit": 5000,        # 枚举检测时的采样限制
    "enum_max_distinct_values": 20,             # 枚举字段最大不同值数量
    "enum_varchar_keywords": [                  # VARCHAR枚举关键词
        "性别", "gender", "状态", "status", "类型", "type", 
        "级别", "level", "方向", "direction", "品类", "classify",
        "模式", "mode", "格式", "format"
    ],
    "large_table_threshold": 1000000,           # 大表阈值（行数）
    
    # 并发配置
    "max_concurrent_tables": 1,                 # 最大并发处理表数（建议保持1，避免LLM并发调用问题）
    
    # LLM配置
    "use_app_config_llm": True,                # 是否使用app_config中的LLM配置
    "comment_generation_timeout": 120,          # LLM调用超时时间(秒)
    "max_llm_retries": 3,                      # LLM调用最大重试次数
    
    # 系统表过滤配置
    "filter_system_tables": True,              # 是否过滤系统表
    "custom_system_prefixes": [],              # 用户自定义系统表前缀
    "custom_system_schemas": [],               # 用户自定义系统schema
    
    # 权限与安全配置
    "check_permissions": True,                 # 是否检查数据库权限
    "require_select_permission": True,         # 是否要求SELECT权限
    "allow_readonly_database": True,           # 是否允许只读数据库
    
    # 错误处理配置
    "continue_on_error": True,                 # 遇到错误是否继续
    "max_table_failures": 5,                  # 最大允许失败表数
    "skip_large_tables": False,               # 是否跳过超大表
    "max_table_size": 10000000,               # 最大表行数限制
    
    # 文件配置
    "ddl_file_suffix": ".ddl",
    "doc_file_suffix": "_detail.md",
    "log_file": "schema_tools.log",
    "create_subdirectories": False,            # 是否创建ddl/docs子目录
    
    # 输出格式配置
    "include_sample_data_in_comments": True,  # 注释中是否包含示例数据
    "max_comment_length": 500,                # 最大注释长度
    "include_field_statistics": True,         # 是否包含字段统计信息
    
    # 调试配置
    "debug_mode": False,                      # 调试模式
    "save_llm_prompts": False,               # 是否保存LLM提示词
    "save_llm_responses": False,             # 是否保存LLM响应
    
    # Question-SQL生成配置
    "qs_generation": {
        "max_tables": 20,                    # 最大表数量限制
        "theme_count": 5,                    # LLM生成的主题数量
        "questions_per_theme": 10,           # 每个主题生成的问题数
        "max_concurrent_themes": 1,          # 并行处理的主题数量
        "continue_on_theme_error": True,     # 主题生成失败是否继续
        "save_intermediate": True,           # 是否保存中间结果
        "output_file_prefix": "qs",          # 输出文件前缀
    },
    
    # SQL验证配置
    "sql_validation": {
        "reuse_connection_pool": True,       # 复用现有连接池
        "max_concurrent_validations": 5,     # 并发验证数
        "validation_timeout": 30,            # 单个验证超时(秒)
        "batch_size": 10,                    # 批处理大小
        "continue_on_error": True,           # 错误时是否继续
        "save_validation_report": True,      # 保存验证报告
        "save_detailed_json_report": False,  # 保存详细JSON报告（可选）
        "readonly_mode": True,               # 启用只读模式
        "max_retry_count": 2,                # 验证失败重试次数
        "report_file_prefix": "sql_validation",  # 报告文件前缀
        
        # SQL修复配置
        "enable_sql_repair": False,          # 启用SQL修复功能（默认禁用）
        "llm_repair_timeout": 120,           # LLM修复超时时间(秒)
        "repair_batch_size": 2,              # 修复批处理大小
        
        # 文件修改配置
        "modify_original_file": False,       # 是否修改原始JSON文件（默认禁用）
    },
    
    # 文件上传配置
    "file_upload": {
        "enabled": True,                     # 是否启用文件上传功能
        "max_file_size_mb": 2,               # 最大文件大小（MB）
        "allowed_extensions": ["txt"],       # 允许的文件扩展名（不带点）
        "target_filename": "table_list.txt", # 上传后的标准文件名
        "validate_content": True,            # 是否验证文件内容
        "min_lines": 1,                      # 最少行数（排除空行和注释）
        "max_lines": 1000,                   # 最大行数限制
        "encoding": "utf-8",                 # 文件编码
        "allow_overwrite": True,             # 是否允许覆盖已存在的文件
    }
}

# 从app_config获取相关配置（如果可用）
if app_config:
    # 继承数据库配置
    if hasattr(app_config, 'PGVECTOR_CONFIG'):
        pgvector_config = app_config.PGVECTOR_CONFIG
        if not SCHEMA_TOOLS_CONFIG["default_db_connection"]:
            SCHEMA_TOOLS_CONFIG["default_db_connection"] = (
                f"postgresql://{pgvector_config['user']}:{pgvector_config['password']}"
                f"@{pgvector_config['host']}:{pgvector_config['port']}/{pgvector_config['dbname']}"
            )

def get_config():
    """获取当前配置"""
    return SCHEMA_TOOLS_CONFIG

def update_config(**kwargs):
    """更新配置"""
    SCHEMA_TOOLS_CONFIG.update(kwargs)

def validate_config():
    """验证配置有效性"""
    errors = []
    
    # 检查必要配置
    if SCHEMA_TOOLS_CONFIG["max_concurrent_tables"] <= 0:
        errors.append("max_concurrent_tables 必须大于0")
    
    if SCHEMA_TOOLS_CONFIG["sample_data_limit"] <= 0:
        errors.append("sample_data_limit 必须大于0")
    
    # 检查处理链配置
    default_pipeline = SCHEMA_TOOLS_CONFIG["default_pipeline"]
    available_pipelines = SCHEMA_TOOLS_CONFIG["available_pipelines"]
    
    if default_pipeline not in available_pipelines:
        errors.append(f"default_pipeline '{default_pipeline}' 不在 available_pipelines 中")
    
    if errors:
        raise ValueError("配置验证失败:\n" + "\n".join(f"  - {error}" for error in errors))
    
    return True

# 启动时验证配置
try:
    validate_config()
except ValueError as e:
    # 在配置文件中使用stderr输出警告，避免依赖logging
    import sys
    print(f"警告: {e}", file=sys.stderr)