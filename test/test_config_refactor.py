#!/usr/bin/env python3
"""
测试配置重构是否成功
"""

def test_config_refactor():
    """测试配置重构"""
    print("=== 配置重构测试 ===")
    
    try:
        import app_config
        print("✓ app_config 导入成功")
    except ImportError as e:
        print(f"✗ app_config 导入失败: {e}")
        return False
    
    # 测试新配置是否存在
    new_configs = [
        'API_DEEPSEEK_CONFIG',
        'API_QWEN_CONFIG', 
        'OLLAMA_EMBEDDING_CONFIG',
        'API_LLM_MODEL',
        'VECTOR_DB_TYPE'
    ]
    
    print("\n--- 新配置检查 ---")
    for config_name in new_configs:
        if hasattr(app_config, config_name):
            print(f"✓ {config_name} 存在")
        else:
            print(f"✗ {config_name} 不存在")
            return False
    
    # 测试旧配置是否已删除
    old_configs = [
        'DEEPSEEK_CONFIG',
        'QWEN_CONFIG',
        'EMBEDDING_OLLAMA_CONFIG',
        'LLM_MODEL_NAME',
        'VECTOR_DB_NAME'
    ]
    
    print("\n--- 旧配置检查 ---")
    for config_name in old_configs:
        if hasattr(app_config, config_name):
            print(f"✗ {config_name} 仍然存在（应该已删除）")
            return False
        else:
            print(f"✓ {config_name} 已删除")
    
    # 测试utils.py中的函数
    print("\n--- Utils函数测试 ---")
    try:
        from common.utils import get_current_llm_config, get_current_embedding_config
        
        # 测试LLM配置
        llm_config = get_current_llm_config()
        print(f"✓ get_current_llm_config() 成功，返回类型: {type(llm_config)}")
        
        # 测试Embedding配置
        embedding_config = get_current_embedding_config()
        print(f"✓ get_current_embedding_config() 成功，返回类型: {type(embedding_config)}")
        
    except Exception as e:
        print(f"✗ Utils函数测试失败: {e}")
        return False
    
    # 测试配置内容
    print("\n--- 配置内容验证 ---")
    try:
        # 验证API_QWEN_CONFIG
        qwen_config = app_config.API_QWEN_CONFIG
        if 'model' in qwen_config and 'api_key' in qwen_config:
            print("✓ API_QWEN_CONFIG 结构正确")
        else:
            print("✗ API_QWEN_CONFIG 结构不正确")
            return False
            
        # 验证API_DEEPSEEK_CONFIG
        deepseek_config = app_config.API_DEEPSEEK_CONFIG
        if 'model' in deepseek_config and 'api_key' in deepseek_config:
            print("✓ API_DEEPSEEK_CONFIG 结构正确")
        else:
            print("✗ API_DEEPSEEK_CONFIG 结构不正确")
            return False
            
        # 验证OLLAMA_EMBEDDING_CONFIG
        ollama_embedding_config = app_config.OLLAMA_EMBEDDING_CONFIG
        if 'model_name' in ollama_embedding_config and 'base_url' in ollama_embedding_config:
            print("✓ OLLAMA_EMBEDDING_CONFIG 结构正确")
        else:
            print("✗ OLLAMA_EMBEDDING_CONFIG 结构不正确")
            return False
            
    except Exception as e:
        print(f"✗ 配置内容验证失败: {e}")
        return False
    
    print("\n=== 配置重构测试完成 ===")
    print("✓ 所有测试通过！配置重构成功！")
    return True

if __name__ == "__main__":
    success = test_config_refactor()
    if not success:
        exit(1) 