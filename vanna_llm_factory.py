"""
Vanna LLM 工厂文件，专注于 ChromaDB 并简化配置。
"""
import app_config, os
from vanna.chromadb import ChromaDB_VectorStore  # 从 Vanna 系统获取
from customqianwen.Custom_QianwenAI_chat import QianWenAI_Chat
from customdeepseek.custom_deepseek_chat import DeepSeekChat
from embedding_function import get_embedding_function
from custompgvector import PG_VectorStore

class Vanna_Qwen_ChromaDB(ChromaDB_VectorStore, QianWenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        QianWenAI_Chat.__init__(self, config=config)

class Vanna_DeepSeek_ChromaDB(ChromaDB_VectorStore, DeepSeekChat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        DeepSeekChat.__init__(self, config=config)

class Vanna_Qwen_PGVector(PG_VectorStore, QianWenAI_Chat):
    def __init__(self, config=None):
        PG_VectorStore.__init__(self, config=config)
        QianWenAI_Chat.__init__(self, config=config)

class Vanna_DeepSeek_PGVector(PG_VectorStore, DeepSeekChat):
    def __init__(self, config=None):
        PG_VectorStore.__init__(self, config=config)
        DeepSeekChat.__init__(self, config=config)

# 组合映射表
LLM_VECTOR_DB_MAP = {
    ('deepseek', 'chromadb'): Vanna_DeepSeek_ChromaDB,
    ('deepseek', 'pgvector'): Vanna_DeepSeek_PGVector,
    ('qwen', 'chromadb'): Vanna_Qwen_ChromaDB,
    ('qwen', 'pgvector'): Vanna_Qwen_PGVector,
}

def create_vanna_instance(config_module=None):
    """
    工厂函数：创建并初始化一个Vanna实例 (LLM 和 ChromaDB 特定版本)
    
    Args:
        config_module: 配置模块，默认为None时使用 app_config
        
    Returns:
        初始化后的Vanna实例
    """
    if config_module is None:
        config_module = app_config

    llm_model_name  = config_module.LLM_MODEL_NAME.lower()
    vector_db_name = config_module.VECTOR_DB_NAME.lower()   

    if (llm_model_name, vector_db_name) not in LLM_VECTOR_DB_MAP:
        raise ValueError(f"不支持的模型类型: {llm_model_name} 或 向量数据库类型: {vector_db_name}")
    
    config = {}
    if llm_model_name == "deepseek":
        config = config_module.DEEPSEEK_CONFIG.copy()
        print(f"创建DeepSeek模型实例，使用模型: {config.get('model', 'deepseek-chat')}")
    elif llm_model_name == "qwen":
        config = config_module.QWEN_CONFIG.copy()
        print(f"创建Qwen模型实例，使用模型: {config.get('model', 'qwen-plus-latest')}")
    else:
        raise ValueError(f"不支持的模型类型: {llm_model_name}") 
    
    if vector_db_name == "chromadb":
        config["path"] = os.path.dirname(os.path.abspath(__file__))
        print(f"已配置使用ChromaDB作为向量数据库，路径：{config['path']}")
    elif vector_db_name == "pgvector":
        # 构建PostgreSQL连接字符串
        pg_config = config_module.PGVECTOR_CONFIG
        connection_string = f"postgresql://{pg_config['user']}:{pg_config['password']}@{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
        config["connection_string"] = connection_string
        print(f"已配置使用PgVector作为向量数据库，连接字符串: {connection_string}")
    else:
        raise ValueError(f"不支持的向量数据库类型: {vector_db_name}")    
    
    embedding_function = get_embedding_function()

    config["embedding_function"] = embedding_function
    print(f"已配置使用 EMBEDDING_CONFIG 中的嵌入模型: {config_module.EMBEDDING_CONFIG['model_name']}, 维度: {config_module.EMBEDDING_CONFIG['embedding_dimension']}")
    
    key = (llm_model_name, vector_db_name)
    cls = LLM_VECTOR_DB_MAP.get(key)
    if cls is None:
        raise ValueError(f"不支持的组合: 模型类型={llm_model_name}, 向量数据库类型={vector_db_name}")
    
    vn = cls(config=config)

    vn.connect_to_postgres(**config_module.APP_DB_CONFIG)           
    print(f"连接到PostgreSQL业务数据库: "
          f"{config_module.APP_DB_CONFIG['host']}:"
          f"{config_module.APP_DB_CONFIG['port']}/"
          f"{config_module.APP_DB_CONFIG['dbname']}")
    return vn
