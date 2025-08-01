"""
全局配置文件
"""
import os
import logging

# --- 项目根目录 ---
# /test/custom_react_agent/config.py -> /
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- LLM 配置 ---
# 在这里写死你的千问API Key
# qwen-plus
# qwen3-235b-a22b
# qwen3-30b-a3b
# sk-8f2320dafc9e4076968accdd8eebd8e9
# my:"sk-db68e37f00974031935395315bfe07f0"
QWEN_API_KEY = "sk-8f2320dafc9e4076968accdd8eebd8e9"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen3-235b-a22b"

# --- Redis 配置 ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_ENABLED = True  # 是否启用Redis状态持久化（LangGraph的AsyncRedisSaver），用于保存对话历史和状态

# 兼容性：保留REDIS_URL用于AsyncRedisSaver
def _build_redis_url():
    """构建Redis连接URL"""
    if REDIS_PASSWORD:
        return f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    else:
        return f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

REDIS_URL = _build_redis_url()

# --- 日志配置 ---
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'

# --- Agent 配置 ---
DEFAULT_USER_ID = "guest"

# --- StateGraph 配置 ---
RECURSION_LIMIT = 100  # StateGraph递归限制

# --- 网络重试配置 ---
MAX_RETRIES = 3                    # 最大重试次数（减少以避免与OpenAI客户端冲突）
RETRY_BASE_DELAY = 3               # 重试基础延迟（秒）
NETWORK_TIMEOUT = 60               # 网络超时时间（秒）- 增加到60秒以应对长上下文处理

# --- HTTP连接管理配置 ---
HTTP_MAX_CONNECTIONS = 10          # 最大连接数
HTTP_MAX_KEEPALIVE_CONNECTIONS = 5 # 最大保持连接数
HTTP_KEEPALIVE_EXPIRY = 30.0       # Keep-Alive过期时间（秒）- 设置为30秒避免服务器断开
HTTP_CONNECT_TIMEOUT = 10.0        # 连接超时（秒）
HTTP_POOL_TIMEOUT = 5.0            # 连接池超时（秒）

# --- 调试配置 ---
DEBUG_MODE = True                  # 调试模式：True=完整日志，False=简化日志
MAX_LOG_LENGTH = 1000              # 非调试模式下的最大日志长度

# --- State管理配置 ---
MESSAGE_TRIM_ENABLED = True        # 是否启用消息裁剪
MESSAGE_TRIM_COUNT = 100          # 消息数量超过此值时触发裁剪，裁剪后保留此数量的消息
MESSAGE_TRIM_SEARCH_LIMIT = 20    # 向前搜索HumanMessage的最大条数 