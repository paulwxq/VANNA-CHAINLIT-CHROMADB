"""
配置相关的工具函数
用于处理不同模型类型的配置选择逻辑
"""

def get_current_embedding_config():
    """
    根据EMBEDDING_MODEL_TYPE返回当前应该使用的embedding配置
    
    Returns:
        dict: 当前的embedding配置字典
        
    Raises:
        ImportError: 如果无法导入app_config
        ValueError: 如果EMBEDDING_MODEL_TYPE值无效
    """
    try:
        import app_config
    except ImportError:
        raise ImportError("无法导入 app_config.py，请确保该文件存在")
    
    if app_config.EMBEDDING_MODEL_TYPE == "ollama":
        return app_config.OLLAMA_EMBEDDING_CONFIG
    elif app_config.EMBEDDING_MODEL_TYPE == "api":
        return app_config.API_EMBEDDING_CONFIG
    else:
        raise ValueError(f"不支持的EMBEDDING_MODEL_TYPE: {app_config.EMBEDDING_MODEL_TYPE}")


def get_current_llm_config():
    """
    根据LLM_MODEL_TYPE和API_LLM_MODEL返回当前应该使用的LLM配置
    
    Returns:
        dict: 当前的LLM配置字典
        
    Raises:
        ImportError: 如果无法导入app_config
        ValueError: 如果LLM_MODEL_TYPE或API_LLM_MODEL值无效
    """
    try:
        import app_config
    except ImportError:
        raise ImportError("无法导入 app_config.py，请确保该文件存在")
    
    if app_config.LLM_MODEL_TYPE == "ollama":
        return app_config.OLLAMA_LLM_CONFIG
    elif app_config.LLM_MODEL_TYPE == "api":
        if app_config.API_LLM_MODEL == "qianwen":
            return app_config.API_QIANWEN_CONFIG
        elif app_config.API_LLM_MODEL == "deepseek":
            return app_config.API_DEEPSEEK_CONFIG
        else:
            raise ValueError(f"不支持的API_LLM_MODEL: {app_config.API_LLM_MODEL}")
    else:
        raise ValueError(f"不支持的LLM_MODEL_TYPE: {app_config.LLM_MODEL_TYPE}")


def get_current_vector_db_config():
    """
    根据VECTOR_DB_TYPE返回当前应该使用的向量数据库配置
    
    Returns:
        dict: 当前的向量数据库配置字典
        
    Raises:
        ImportError: 如果无法导入app_config
        ValueError: 如果VECTOR_DB_TYPE值无效
    """
    try:
        import app_config
    except ImportError:
        raise ImportError("无法导入 app_config.py，请确保该文件存在")
    
    if app_config.VECTOR_DB_TYPE == "pgvector":
        return app_config.PGVECTOR_CONFIG
    elif app_config.VECTOR_DB_TYPE == "chromadb":
        # ChromaDB通常不需要复杂配置，返回项目根目录路径
        import os
        return {"path": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}
    else:
        raise ValueError(f"不支持的VECTOR_DB_TYPE: {app_config.VECTOR_DB_TYPE}")


def get_current_model_info():
    """
    获取当前配置的模型信息摘要
    
    Returns:
        dict: 包含当前所有模型配置信息的字典
        
    Raises:
        ImportError: 如果无法导入app_config
    """
    try:
        import app_config
    except ImportError:
        raise ImportError("无法导入 app_config.py，请确保该文件存在")
    
    # 获取LLM模型名称
    if app_config.LLM_MODEL_TYPE == "ollama":
        llm_model_name = app_config.OLLAMA_LLM_CONFIG.get("model", "unknown")
    else:
        llm_model_name = app_config.API_LLM_MODEL
    
    # 获取Embedding模型名称
    if app_config.EMBEDDING_MODEL_TYPE == "ollama":
        embedding_model_name = app_config.OLLAMA_EMBEDDING_CONFIG.get("model_name", "unknown")
    else:
        embedding_model_name = app_config.API_EMBEDDING_CONFIG.get("model_name", "unknown")
    
    return {
        "llm_type": app_config.LLM_MODEL_TYPE,
        "llm_model": llm_model_name,
        "embedding_type": app_config.EMBEDDING_MODEL_TYPE,
        "embedding_model": embedding_model_name,
        "vector_db": app_config.VECTOR_DB_TYPE
    }


def is_using_ollama_llm():
    """
    检查当前是否使用Ollama作为LLM提供商
    
    Returns:
        bool: 如果使用Ollama LLM返回True，否则返回False
    """
    try:
        import app_config
        return app_config.LLM_MODEL_TYPE == "ollama"
    except ImportError:
        return False


def is_using_ollama_embedding():
    """
    检查当前是否使用Ollama作为Embedding提供商
    
    Returns:
        bool: 如果使用Ollama Embedding返回True，否则返回False
    """
    try:
        import app_config
        return app_config.EMBEDDING_MODEL_TYPE == "ollama"
    except ImportError:
        return False


def is_using_api_llm():
    """
    检查当前是否使用API作为LLM提供商
    
    Returns:
        bool: 如果使用API LLM返回True，否则返回False
    """
    try:
        import app_config
        return app_config.LLM_MODEL_TYPE == "api"
    except ImportError:
        return False


def is_using_api_embedding():
    """
    检查当前是否使用API作为Embedding提供商
    
    Returns:
        bool: 如果使用API Embedding返回True，否则返回False
    """
    try:
        import app_config
        return app_config.EMBEDDING_MODEL_TYPE == "api"
    except ImportError:
        return False


def print_current_config():
    """
    打印当前的配置信息，用于调试和确认配置
    """
    try:
        model_info = get_current_model_info()
        print("=== 当前模型配置 ===")
        print(f"LLM提供商: {model_info['llm_type']}")
        print(f"LLM模型: {model_info['llm_model']}")
        print(f"Embedding提供商: {model_info['embedding_type']}")
        print(f"Embedding模型: {model_info['embedding_model']}")
        print(f"向量数据库: {model_info['vector_db']}")
        print("==================")
    except Exception as e:
        print(f"无法获取配置信息: {e}") 