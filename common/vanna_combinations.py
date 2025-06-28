"""
Vanna LLM与向量数据库的组合类
统一管理所有LLM提供商与向量数据库的组合
"""
from core.logging import get_app_logger

# 初始化logger
_logger = get_app_logger("VannaCombinations")

# 向量数据库导入
from vanna.chromadb import ChromaDB_VectorStore
try:
    from custompgvector import PG_VectorStore
except ImportError:
    _logger.warning("无法导入 PG_VectorStore，PGVector相关组合类将不可用")
    PG_VectorStore = None

# LLM提供商导入 - 使用新的重构后的实现
from customllm.qianwen_chat import QianWenChat
from customllm.deepseek_chat import DeepSeekChat
try:
    from customllm.ollama_chat import OllamaChat
except ImportError:
    _logger.warning("无法导入 OllamaChat，Ollama相关组合类将不可用")
    OllamaChat = None


# ===== API LLM + ChromaDB 组合 =====

class QianWenChromaDB(ChromaDB_VectorStore, QianWenChat):
    """QianWen LLM + ChromaDB 向量数据库组合"""
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        QianWenChat.__init__(self, config=config)


class DeepSeekChromaDB(ChromaDB_VectorStore, DeepSeekChat):
    """DeepSeek LLM + ChromaDB 向量数据库组合"""
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        DeepSeekChat.__init__(self, config=config)


# ===== API LLM + PGVector 组合 =====

if PG_VectorStore is not None:
    class QianWenPGVector(PG_VectorStore, QianWenChat):
        """QianWen LLM + PGVector 向量数据库组合"""
        def __init__(self, config=None):
            PG_VectorStore.__init__(self, config=config)
            QianWenChat.__init__(self, config=config)

    class DeepSeekPGVector(PG_VectorStore, DeepSeekChat):
        """DeepSeek LLM + PGVector 向量数据库组合"""
        def __init__(self, config=None):
            PG_VectorStore.__init__(self, config=config)
            DeepSeekChat.__init__(self, config=config)
else:
    # 如果PG_VectorStore不可用，创建占位符类
    class QianWenPGVector:
        def __init__(self, config=None):
            raise ImportError("PG_VectorStore 不可用，无法创建 QianWenPGVector 实例")
    
    class DeepSeekPGVector:
        def __init__(self, config=None):
            raise ImportError("PG_VectorStore 不可用，无法创建 DeepSeekPGVector 实例")


# ===== Ollama LLM + ChromaDB 组合 =====

if OllamaChat is not None:
    class OllamaChromaDB(ChromaDB_VectorStore, OllamaChat):
        """Ollama LLM + ChromaDB 向量数据库组合"""
        def __init__(self, config=None):
            ChromaDB_VectorStore.__init__(self, config=config)
            OllamaChat.__init__(self, config=config)
else:
    class OllamaChromaDB:
        def __init__(self, config=None):
            raise ImportError("OllamaChat 不可用，无法创建 OllamaChromaDB 实例")


# ===== Ollama LLM + PGVector 组合 =====

if OllamaChat is not None and PG_VectorStore is not None:
    class OllamaPGVector(PG_VectorStore, OllamaChat):
        """Ollama LLM + PGVector 向量数据库组合"""
        def __init__(self, config=None):
            PG_VectorStore.__init__(self, config=config)
            OllamaChat.__init__(self, config=config)
else:
    class OllamaPGVector:
        def __init__(self, config=None):
            error_msg = []
            if OllamaChat is None:
                error_msg.append("OllamaChat 不可用")
            if PG_VectorStore is None:
                error_msg.append("PG_VectorStore 不可用")
            raise ImportError(f"{', '.join(error_msg)}，无法创建 OllamaPGVector 实例")


# ===== 组合类映射表 =====

# LLM类型到类名的映射
LLM_CLASS_MAP = {
    "qianwen": {
        "chromadb": QianWenChromaDB,
        "pgvector": QianWenPGVector,
    },
    "deepseek": {
        "chromadb": DeepSeekChromaDB,
        "pgvector": DeepSeekPGVector,
    },
    "ollama": {
        "chromadb": OllamaChromaDB,
        "pgvector": OllamaPGVector,
    }
}


def get_vanna_class(llm_type: str, vector_db_type: str):
    """
    根据LLM类型和向量数据库类型获取对应的Vanna组合类
    
    Args:
        llm_type: LLM类型 ("qianwen", "deepseek", "ollama")
        vector_db_type: 向量数据库类型 ("chromadb", "pgvector")
        
    Returns:
        对应的Vanna组合类
        
    Raises:
        ValueError: 如果不支持的组合类型
    """
    llm_type = llm_type.lower()
    vector_db_type = vector_db_type.lower()
    
    if llm_type not in LLM_CLASS_MAP:
        raise ValueError(f"不支持的LLM类型: {llm_type}，支持的类型: {list(LLM_CLASS_MAP.keys())}")
    
    if vector_db_type not in LLM_CLASS_MAP[llm_type]:
        raise ValueError(f"不支持的向量数据库类型: {vector_db_type}，支持的类型: {list(LLM_CLASS_MAP[llm_type].keys())}")
    
    return LLM_CLASS_MAP[llm_type][vector_db_type]


def list_available_combinations():
    """
    列出所有可用的LLM与向量数据库组合
    
    Returns:
        dict: 可用组合的字典
    """
    available = {}
    
    for llm_type, vector_dbs in LLM_CLASS_MAP.items():
        available[llm_type] = []
        for vector_db_type, cls in vector_dbs.items():
            try:
                # 尝试创建实例来检查是否可用
                cls(config={})
                available[llm_type].append(vector_db_type)
            except ImportError:
                # 如果导入错误，说明不可用
                continue
            except Exception:
                # 其他错误（如配置错误）仍然认为是可用的
                available[llm_type].append(vector_db_type)
    
    return available


def print_available_combinations():
    """打印所有可用的组合"""
    _logger.info("可用的LLM与向量数据库组合:")
    _logger.info("=" * 40)
    
    combinations = list_available_combinations()
    
    for llm_type, vector_dbs in combinations.items():
        _logger.info(f"\n{llm_type.upper()} LLM:")
        for vector_db in vector_dbs:
            class_name = LLM_CLASS_MAP[llm_type][vector_db].__name__
            _logger.info(f"  + {vector_db} -> {class_name}")
    
    if not any(combinations.values()):
        _logger.warning("没有可用的组合，请检查依赖是否正确安装")


# ===== 向后兼容性支持 =====

# 为了保持向后兼容，可以在这里添加别名
# 例如：
# VannaQwenChromaDB = QianWenChromaDB  # 旧的命名风格 