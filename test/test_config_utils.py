#!/usr/bin/env python3
"""
测试配置工具函数的脚本
用于验证common/utils.py中的函数是否正常工作
"""

def test_config_utils():
    """测试配置工具函数"""
    try:
        from common.utils import (
            get_current_embedding_config,
            get_current_llm_config,
            get_current_vector_db_config,
            get_current_model_info,
            is_using_ollama_llm,
            is_using_ollama_embedding,
            is_using_api_llm,
            is_using_api_embedding,
            print_current_config
        )
        
        print("=== 测试配置工具函数 ===")
        
        # 测试模型类型检查函数
        print(f"使用Ollama LLM: {is_using_ollama_llm()}")
        print(f"使用Ollama Embedding: {is_using_ollama_embedding()}")
        print(f"使用API LLM: {is_using_api_llm()}")
        print(f"使用API Embedding: {is_using_api_embedding()}")
        print()
        
        # 测试配置获取函数
        print("=== LLM配置 ===")
        llm_config = get_current_llm_config()
        for key, value in llm_config.items():
            if key == "api_key" and value:
                print(f"{key}: {'*' * 8}...{value[-4:]}")  # 隐藏API密钥
            else:
                print(f"{key}: {value}")
        print()
        
        print("=== Embedding配置 ===")
        embedding_config = get_current_embedding_config()
        for key, value in embedding_config.items():
            if key == "api_key" and value:
                print(f"{key}: {'*' * 8}...{value[-4:]}")  # 隐藏API密钥
            else:
                print(f"{key}: {value}")
        print()
        
        print("=== 向量数据库配置 ===")
        vector_db_config = get_current_vector_db_config()
        for key, value in vector_db_config.items():
            if key == "password" and value:
                print(f"{key}: {'*' * 8}")  # 隐藏密码
            else:
                print(f"{key}: {value}")
        print()
        
        # 测试模型信息摘要
        print("=== 模型信息摘要 ===")
        model_info = get_current_model_info()
        for key, value in model_info.items():
            print(f"{key}: {value}")
        print()
        
        # 测试打印配置函数
        print_current_config()
        
        print("✅ 所有配置工具函数测试通过！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_different_configurations():
    """测试不同配置组合"""
    import app_config
    
    print("\n=== 测试不同配置组合 ===")
    
    # 保存原始配置
    original_llm_type = app_config.LLM_MODEL_TYPE
    original_embedding_type = app_config.EMBEDDING_MODEL_TYPE
    original_llm_name = app_config.LLM_MODEL_NAME
    
    try:
        from common.utils import get_current_model_info, print_current_config
        
        # 测试配置1：API LLM + API Embedding
        print("\n--- 配置1：API LLM + API Embedding ---")
        app_config.LLM_MODEL_TYPE = "api"
        app_config.EMBEDDING_MODEL_TYPE = "api"
        app_config.LLM_MODEL_NAME = "qwen"
        print_current_config()
        
        # 测试配置2：API LLM + Ollama Embedding
        print("\n--- 配置2：API LLM + Ollama Embedding ---")
        app_config.LLM_MODEL_TYPE = "api"
        app_config.EMBEDDING_MODEL_TYPE = "ollama"
        app_config.LLM_MODEL_NAME = "deepseek"
        print_current_config()
        
        # 测试配置3：Ollama LLM + API Embedding
        print("\n--- 配置3：Ollama LLM + API Embedding ---")
        app_config.LLM_MODEL_TYPE = "ollama"
        app_config.EMBEDDING_MODEL_TYPE = "api"
        print_current_config()
        
        # 测试配置4：Ollama LLM + Ollama Embedding
        print("\n--- 配置4：Ollama LLM + Ollama Embedding ---")
        app_config.LLM_MODEL_TYPE = "ollama"
        app_config.EMBEDDING_MODEL_TYPE = "ollama"
        print_current_config()
        
    except Exception as e:
        print(f"❌ 配置测试失败: {e}")
    finally:
        # 恢复原始配置
        app_config.LLM_MODEL_TYPE = original_llm_type
        app_config.EMBEDDING_MODEL_TYPE = original_embedding_type
        app_config.LLM_MODEL_NAME = original_llm_name
        print("\n--- 恢复原始配置 ---")
        print_current_config()

if __name__ == "__main__":
    test_config_utils()
    test_different_configurations() 