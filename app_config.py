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

# =====API 模型名称配置 =====
# API LLM模型名称（当LLM_MODEL_TYPE="api"时使用：qianwen 或 deepseek ）
API_LLM_MODEL = "qianwen"

# 向量数据库类型：chromadb 或 pgvector
VECTOR_DB_TYPE = "pgvector"

# ===== API LLM模型配置 =====
# DeepSeek模型配置
API_DEEPSEEK_CONFIG = {
    "api_key": os.getenv("DEEPSEEK_API_KEY"),  # 从环境变量读取API密钥
    "base_url": "https://api.deepseek.com",  # DeepSeek API地址
    "model": "deepseek-reasoner",  # deepseek-chat, deepseek-reasoner
    "allow_llm_to_see_data": True,
    "temperature": 0.6,
    "n_results": 6,
    "language": "Chinese",
    "stream": True,  # 是否使用流式模式
    "enable_thinking": False  # 自定义，是否支持流模式
}

# Qwen模型配置
API_QIANWEN_CONFIG = {
    "api_key": os.getenv("QWEN_API_KEY"),  # 从环境变量读取API密钥
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 千问API地址
    "model": "qwen-plus-latest",
    "allow_llm_to_see_data": True,
    "temperature": 0.6,
    "n_results": 6,
    "language": "Chinese",
    "stream": False,  # 是否使用流式模式
    "enable_thinking": False  # 是否启用思考功能（要求stream=True）
}
#qwen3-30b-a3b
#qwen3-235b-a22b
#qwen-plus-latest
#qwen-plus

# ===== API Embedding模型配置 =====
API_EMBEDDING_CONFIG = {
    "model_name": "text-embedding-v4",
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
    "timeout": 60,  # Ollama可能需要更长超时时间
    "stream": True,  # 是否使用流式模式
    "enable_thinking": True,  # 是否启用思考功能（推理模型支持）
    
    # Ollama 特定参数
    #"num_ctx": 8192,  # 上下文长度
    #"num_predict": 2048,  # 预测token数量，-1表示无限制
    #"repeat_penalty": 1.1,  # 重复惩罚
    #"auto_check_connection": True  # 是否自动检查连接
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
    "port": 6432,
    "dbname": "highway_db",
    "user": os.getenv("APP_DB_USER"),
    "password": os.getenv("APP_DB_PASSWORD")
}

# ChromaDB配置
# CHROMADB_PATH = "."  

# PgVector数据库连接配置 (向量数据库，独立于业务数据库)
PGVECTOR_CONFIG = {
    "host": "192.168.67.1",
    "port": 5432,
    "dbname": "highway_pgvector_db",
    "user": os.getenv("PGVECTOR_DB_USER"),
    "password": os.getenv("PGVECTOR_DB_PASSWORD")
}

# 训练脚本批处理配置
# 这些配置仅用于 training/run_training.py 训练脚本的批处理优化
# 注意：当使用阿里云等API服务时，建议关闭批处理或设置单线程以避免并发连接错误
TRAINING_BATCH_PROCESSING_ENABLED = False   # 是否启用训练数据批处理（关闭以避免并发问题）
TRAINING_BATCH_SIZE = 10                    # 每批处理的训练项目数量
TRAINING_MAX_WORKERS = 1                    # 训练批处理的最大工作线程数（设置为1确保单线程）


# 是否启用问题重写功能，也就是上下文问题合并。
REWRITE_QUESTION_ENABLED = False

# 是否启用数据库查询结果摘要生成
# True: 执行完SQL后生成摘要（默认）
# False: 只返回SQL执行结果，跳过摘要生成，节省LLM调用
ENABLE_RESULT_SUMMARY = True

# 是否在返回结果中显示thinking过程
# True: 显示 <think></think> 内容
# False: 隐藏 <think></think> 内容，只显示最终答案
# 此参数影响：摘要生成、SQL生成解释性文本、API返回结果等所有输出内容
DISPLAY_RESULT_THINKING = False

# 是否启用向量查询结果得分阈值过滤
# result = max((n + 1) // 2, 1)
ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True
# 向量查询结果得分阈值
RESULT_VECTOR_SQL_SCORE_THRESHOLD = 0.65
RESULT_VECTOR_DDL_SCORE_THRESHOLD = 0.5
RESULT_VECTOR_DOC_SCORE_THRESHOLD = 0.5

ENABLE_ERROR_SQL_PROMPT = True
RESULT_VECTOR_ERROR_SQL_SCORE_THRESHOLD = 0.8

# 接口返回查询记录的最大行数
API_MAX_RETURN_ROWS = 1000


# 仅LLM分类:"llm_only", 直接数据库查询："database_direct", 直接聊天对话: "chat_direct", 混合模式: "hybrid"
# 混合模式 hybrid（推荐）
QUESTION_ROUTING_MODE = "hybrid"

# ==================== Redis对话管理配置 ====================

# 对话上下文配置
CONVERSATION_CONTEXT_COUNT = 2          # 传递给LLM的上下文消息条数
CONVERSATION_MAX_LENGTH = 10            # 单个对话最大消息数
USER_MAX_CONVERSATIONS = 5              # 用户最大对话数

# 用户管理配置
DEFAULT_ANONYMOUS_USER = "guest"        # 匿名用户统一ID

# Redis配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None

# 缓存开关配置
ENABLE_CONVERSATION_CONTEXT = True      # 是否启用对话上下文
ENABLE_QUESTION_ANSWER_CACHE = False     # 是否启用问答结果缓存
ENABLE_EMBEDDING_CACHE = True           # 是否启用embedding向量缓存

# TTL配置（单位：秒）
CONVERSATION_TTL = 7 * 24 * 3600        # 对话保存7天
USER_CONVERSATIONS_TTL = 7 * 24 * 3600  # 用户对话列表保存7天（所有用户统一）
QUESTION_ANSWER_TTL = 24 * 3600         # 问答结果缓存24小时
EMBEDDING_CACHE_TTL = 30 * 24 * 3600    # embedding向量缓存30天

# Embedding缓存管理配置
EMBEDDING_CACHE_MAX_SIZE = 5000        # 最大缓存问题数量