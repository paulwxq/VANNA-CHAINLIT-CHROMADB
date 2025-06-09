"""
Vanna LLM 工厂文件，支持多种LLM提供商和向量数据库
"""
import app_config, os
from embedding_function import get_embedding_function
from common.vanna_combinations import get_vanna_class, print_available_combinations

def create_vanna_instance(config_module=None):
    """
    工厂函数：创建并初始化一个Vanna实例
    支持API和Ollama两种LLM提供商，以及ChromaDB和PgVector两种向量数据库
    
    Args:
        config_module: 配置模块，默认为None时使用 app_config
        
    Returns:
        初始化后的Vanna实例
    """
    if config_module is None:
        config_module = app_config

    try:
        from common.utils import (
            get_current_llm_config, 
            get_current_vector_db_config,
            get_current_model_info,
            is_using_ollama_llm,
            print_current_config
        )
    except ImportError:
        raise ImportError("无法导入 common.utils，请确保该文件存在")

    # 打印当前配置信息
    print_current_config()
    
    # 获取当前配置
    llm_config = get_current_llm_config()
    vector_db_config = get_current_vector_db_config()
    model_info = get_current_model_info()
    
    # 获取对应的Vanna组合类
    try:
        if is_using_ollama_llm():
            llm_type = "ollama"
        else:
            llm_type = model_info["llm_model"].lower()
        
        vector_db_type = model_info["vector_db"].lower()
        
        cls = get_vanna_class(llm_type, vector_db_type)
        print(f"创建{llm_type.upper()}+{vector_db_type.upper()}实例")
        
    except ValueError as e:
        print(f"错误: {e}")
        print("\n可用的组合:")
        print_available_combinations()
        raise
    
    # 准备配置
    config = llm_config.copy()
    
    # 配置向量数据库
    if model_info["vector_db"] == "chromadb":
        config["path"] = os.path.dirname(os.path.abspath(__file__))
        print(f"已配置使用ChromaDB，路径：{config['path']}")
    elif model_info["vector_db"] == "pgvector":
        # 构建PostgreSQL连接字符串
        connection_string = f"postgresql://{vector_db_config['user']}:{vector_db_config['password']}@{vector_db_config['host']}:{vector_db_config['port']}/{vector_db_config['dbname']}"
        config["connection_string"] = connection_string
        print(f"已配置使用PgVector，连接字符串: {connection_string}")
    
    # 配置embedding函数
    embedding_function = get_embedding_function()
    config["embedding_function"] = embedding_function
    print(f"已配置使用{model_info['embedding_type'].upper()}嵌入模型: {model_info['embedding_model']}")
    
    # 创建实例
    vn = cls(config=config)

    # 连接到业务数据库
    vn.connect_to_postgres(**config_module.APP_DB_CONFIG)           
    print(f"已连接到业务数据库: "
          f"{config_module.APP_DB_CONFIG['host']}:"
          f"{config_module.APP_DB_CONFIG['port']}/"
          f"{config_module.APP_DB_CONFIG['dbname']}")
    
    return vn
