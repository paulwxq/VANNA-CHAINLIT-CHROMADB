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
QWEN_API_KEY = "sk-db68e37f00974031935395315bfe07f0"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen3-30b-a3b"

# --- Redis 配置 ---
REDIS_URL = "redis://localhost:6379"
REDIS_ENABLED = True

# --- 日志配置 ---
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'

# --- Agent 配置 ---
DEFAULT_USER_ID = "guest"

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