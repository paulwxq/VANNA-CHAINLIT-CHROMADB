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
QWEN_API_KEY = "sk-db68e37f00974031935395315bfe07f0"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen3-235b-a22b"

# --- Redis 配置 ---
REDIS_URL = "redis://localhost:6379"
REDIS_ENABLED = True

# --- 日志配置 ---
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'

# --- Agent 配置 ---
DEFAULT_USER_ID = "default-user" 