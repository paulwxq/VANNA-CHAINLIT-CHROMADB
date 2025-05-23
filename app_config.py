from dotenv import load_dotenv
import os

# 加载.env文件中的环境变量
load_dotenv()

# 使用的模型类型（"qwen" 或 "deepseek"）
MODEL_TYPE = "qwen"

# DeepSeek模型配置
DEEPSEEK_CONFIG = {
    "api_key": os.getenv("DEEPSEEK_API_KEY"),  # 从环境变量读取API密钥
    "model": "deepseek-reasoner",  # deepseek-chat, deepseek-reasoner
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "enable_thinking": False  # 自定义，是否支持流模式
}


# Qwen模型配置
QWEN_CONFIG = {
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

EMBEDDING_CONFIG = {
    "model_name": "BAAI/bge-m3",
    "api_key": os.getenv("EMBEDDING_API_KEY"),
    "base_url": os.getenv("EMBEDDING_BASE_URL"),
    "embedding_dimension": 1024
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

# 批处理配置
BATCH_PROCESSING_ENABLED = True
BATCH_SIZE = 10
MAX_WORKERS = 4