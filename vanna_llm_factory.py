"""
Vanna LLM 工厂文件，专注于 ChromaDB 并简化配置。
"""
from vanna.chromadb import ChromaDB_VectorStore  # 从 Vanna 系统获取
from customqianwen.Custom_QianwenAI_chat import QianWenAI_Chat
from customdeepseek.custom_deepseek_chat import DeepSeekChat
import app_config 
from embedding_function import get_embedding_function
import os

class Vanna_Qwen_ChromaDB(ChromaDB_VectorStore, QianWenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        QianWenAI_Chat.__init__(self, config=config)

class Vanna_DeepSeek_ChromaDB(ChromaDB_VectorStore, DeepSeekChat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        DeepSeekChat.__init__(self, config=config)

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

    model_type = config_module.MODEL_TYPE.lower()
    
    config = {}
    if model_type == "deepseek":
        config = config_module.DEEPSEEK_CONFIG.copy()
        print(f"创建DeepSeek模型实例，使用模型: {config['model']}")
        # 检查API密钥
        if not config.get("api_key"):
            print(f"\n错误: DeepSeek API密钥未设置或为空")
            print(f"请在.env文件中设置DEEPSEEK_API_KEY环境变量")
            print(f"无法继续执行，程序退出\n")
            import sys
            sys.exit(1)
    elif model_type == "qwen":
        config = config_module.QWEN_CONFIG.copy()
        print(f"创建Qwen模型实例，使用模型: {config['model']}")
        # 检查API密钥
        if not config.get("api_key"):
            print(f"\n错误: Qwen API密钥未设置或为空")
            print(f"请在.env文件中设置QWEN_API_KEY环境变量")
            print(f"无法继续执行，程序退出\n")
            import sys
            sys.exit(1)
    else:
        raise ValueError(f"不支持的模型类型: {model_type}") 
    
    embedding_function = get_embedding_function()

    config["embedding_function"] = embedding_function
    print(f"已配置使用 EMBEDDING_CONFIG 中的嵌入模型: {config_module.EMBEDDING_CONFIG['model_name']}, 维度: {config_module.EMBEDDING_CONFIG['embedding_dimension']}")
    
    # 设置ChromaDB路径为项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    config["path"] = project_root
    print(f"已配置使用ChromaDB作为向量数据库，路径：{project_root}")
    
    vn = None
    if model_type == "deepseek":
        vn = Vanna_DeepSeek_ChromaDB(config=config)
        print("创建DeepSeek+ChromaDB实例")
    elif model_type == "qwen":
        vn = Vanna_Qwen_ChromaDB(config=config)
        print("创建Qwen+ChromaDB实例")
    
    if vn is None:
        raise ValueError(f"未能成功创建Vanna实例，不支持的模型类型: {model_type}")

    vn.connect_to_postgres(**config_module.APP_DB_CONFIG)           
    print(f"已连接到业务数据库: "
          f"{config_module.APP_DB_CONFIG['host']}:"
          f"{config_module.APP_DB_CONFIG['port']}/"
          f"{config_module.APP_DB_CONFIG['dbname']}")
    return vn
