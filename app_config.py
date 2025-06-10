from dotenv import load_dotenv
import os

# 加载.env文件中的环境变量
# 使用 override=True 确保能够重新加载更新的环境变量
load_dotenv(override=True)

# ===== 模型提供商类型配置 =====
# LLM模型提供商类型：api 或 ollama
LLM_MODEL_TYPE = "api"  # api, ollama

# Embedding模型提供商类型：api 或 ollama  
EMBEDDING_MODEL_TYPE = "api"  # api, ollama

# ===== 模型名称配置 =====
# API LLM模型名称（当LLM_MODEL_TYPE="api"时使用：qwen 或 deepseek）
API_LLM_MODEL = "qwen"

# 向量数据库类型：chromadb 或 pgvector
VECTOR_DB_TYPE = "pgvector"

# ===== API LLM模型配置 =====
# DeepSeek模型配置
API_DEEPSEEK_CONFIG = {
    "api_key": os.getenv("DEEPSEEK_API_KEY"),  # 从环境变量读取API密钥
    "model": "deepseek-reasoner",  # deepseek-chat, deepseek-reasoner
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "enable_thinking": False  # 自定义，是否支持流模式
}

# Qwen模型配置
API_QWEN_CONFIG = {
    "api_key": os.getenv("QWEN_API_KEY"),  # 从环境变量读取API密钥
    "model": "qwen-plus",
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "enable_thinking": False #自定义，是否支持流模式，仅qwen3模型。
}
#qwen3-30b-a3b
#qwen3-235b-a22b
#qwen-plus-latest
#qwen-plus

# ===== API Embedding模型配置 =====
API_EMBEDDING_CONFIG = {
    "model_name": "BAAI/bge-m3",
    "api_key": os.getenv("EMBEDDING_API_KEY"),
    "base_url": os.getenv("EMBEDDING_BASE_URL"),
    "embedding_dimension": 1024
}

# BAAI/bge-m3
# text-embedding-v4

# ===== Ollama LLM模型配置 =====
OLLAMA_LLM_CONFIG = {
    "base_url": "http://192.168.3.204:11434",  # Ollama服务地址
    "model": "qwen3:32b",  # Ollama模型名称，如：qwen3:32b, deepseek-r1:32b
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "timeout": 60  # Ollama可能需要更长超时时间
}


# ===== Ollama Embedding模型配置 =====
OLLAMA_EMBEDDING_CONFIG = {
    "base_url": "http://192.168.3.204:11434",  # Ollama服务地址
    "model_name": "bge-m3:567m",  # Ollama embedding模型名称
    "embedding_dimension": 1024  # 根据实际模型调整
}



# 应用数据库连接配置 (业务数据库)
APP_DB_CONFIG = {
    "host": "192.168.67.1",
    "port": 5432,
    "dbname": "bank_db",
    "user": os.getenv("APP_DB_USER"),
    "password": os.getenv("APP_DB_PASSWORD")
}

# ChromaDB配置
# CHROMADB_PATH = "."  

# PgVector数据库连接配置 (向量数据库，独立于业务数据库)
PGVECTOR_CONFIG = {
    "host": "192.168.67.1",
    "port": 5432,
    "dbname": "pgvector_db",
    "user": os.getenv("PGVECTOR_DB_USER"),
    "password": os.getenv("PGVECTOR_DB_PASSWORD")
}

# 训练脚本批处理配置
# 这些配置仅用于 training/run_training.py 训练脚本的批处理优化
TRAINING_BATCH_PROCESSING_ENABLED = True    # 是否启用训练数据批处理
TRAINING_BATCH_SIZE = 10                    # 每批处理的训练项目数量
TRAINING_MAX_WORKERS = 4                    # 训练批处理的最大工作线程数

# 训练数据路径配置
# 支持以下格式：
# 1. 相对路径（以 . 开头）：
#    "./training/data"     - 项目根目录下的training/data
#    "../data"             - 项目根目录上级的data目录
# 2. 绝对路径：
#    "/home/user/data"     - Linux绝对路径
#    "C:/data"             - Windows绝对路径
#    "D:\\training\\data"  - Windows绝对路径（转义反斜杠）
# 3. 相对路径（不以.开头）：
#    "training/data"       - 相对于项目根目录
#    "my_data"             - 项目根目录下的my_data文件夹
TRAINING_DATA_PATH = "./training/data"

# 是否启用问题重写功能，也就是上下文问题合并。
REWRITE_QUESTION_ENABLED = False

# 是否启用向量查询结果得分阈值过滤
# result = max((n + 1) // 2, 1)
ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True
# 向量查询结果得分阈值
RESULT_VECTOR_SQL_SCORE_THRESHOLD = 0.65
RESULT_VECTOR_DDL_SCORE_THRESHOLD = 0.5
RESULT_VECTOR_DOC_SCORE_THRESHOLD = 0.5
RESULT_VECTOR_ERROR_SQL_SCORE_THRESHOLD = 0.5

ENABLE_ERROR_SQL_PROMPT = True