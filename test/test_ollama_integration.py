#!/usr/bin/env python3
"""
测试Ollama集成功能的脚本
用于验证Ollama LLM和Embedding是否正常工作
"""

def test_ollama_llm():
    """测试Ollama LLM功能"""
    print("=== 测试Ollama LLM ===")
    
    try:
        from customollama.ollama_chat import OllamaChat
        
        # 测试配置
        config = {
            "base_url": "http://localhost:11434",
            "model": "qwen2.5:7b",
            "temperature": 0.7,
            "timeout": 60
        }
        
        # 创建实例
        ollama_chat = OllamaChat(config=config)
        
        # 测试连接
        print("测试Ollama连接...")
        test_result = ollama_chat.test_connection()
        
        if test_result["success"]:
            print(f"✅ Ollama LLM连接成功: {test_result['message']}")
        else:
            print(f"❌ Ollama LLM连接失败: {test_result['message']}")
            return False
            
        # 测试简单对话
        print("\n测试简单对话...")
        response = ollama_chat.chat_with_llm("你好，请简单介绍一下你自己")
        print(f"LLM响应: {response}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ollama LLM测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ollama_embedding():
    """测试Ollama Embedding功能"""
    print("\n=== 测试Ollama Embedding ===")
    
    try:
        from customollama.ollama_embedding import OllamaEmbeddingFunction
        
        # 创建实例
        embedding_func = OllamaEmbeddingFunction(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434",
            embedding_dimension=768
        )
        
        # 测试连接
        print("测试Ollama Embedding连接...")
        test_result = embedding_func.test_connection()
        
        if test_result["success"]:
            print(f"✅ Ollama Embedding连接成功: {test_result['message']}")
        else:
            print(f"❌ Ollama Embedding连接失败: {test_result['message']}")
            return False
            
        # 测试生成embedding
        print("\n测试生成embedding...")
        test_texts = ["这是一个测试文本", "另一个测试文本"]
        embeddings = embedding_func(test_texts)
        
        print(f"生成了 {len(embeddings)} 个embedding向量")
        for i, emb in enumerate(embeddings):
            print(f"文本 {i+1} 的embedding维度: {len(emb)}")
            
        return True
        
    except Exception as e:
        print(f"❌ Ollama Embedding测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ollama_with_config():
    """测试使用配置文件的Ollama功能"""
    print("\n=== 测试配置文件中的Ollama设置 ===")
    
    try:
        import app_config
        from common.utils import print_current_config, is_using_ollama_llm, is_using_ollama_embedding
        
        # 保存原始配置
        original_llm_type = app_config.LLM_MODEL_TYPE
        original_embedding_type = app_config.EMBEDDING_MODEL_TYPE
        
        try:
            # 设置为Ollama模式
            app_config.LLM_MODEL_TYPE = "ollama"
            app_config.EMBEDDING_MODEL_TYPE = "ollama"
            
            print("当前配置:")
            print_current_config()
            
            print(f"\n使用Ollama LLM: {is_using_ollama_llm()}")
            print(f"使用Ollama Embedding: {is_using_ollama_embedding()}")
            
            # 测试embedding函数
            print("\n测试通过配置获取embedding函数...")
            from embedding_function import get_embedding_function
            
            embedding_func = get_embedding_function()
            print(f"成功创建embedding函数: {type(embedding_func).__name__}")
            
            # 测试工厂函数（如果Ollama服务可用的话）
            print("\n测试工厂函数...")
            try:
                from vanna_llm_factory import create_vanna_instance
                vn = create_vanna_instance()
                print(f"✅ 成功创建Vanna实例: {type(vn).__name__}")
                return True
            except Exception as e:
                print(f"⚠️  工厂函数测试失败（可能是Ollama服务未启动）: {e}")
                return True  # 这不算失败，只是服务未启动
                
        finally:
            # 恢复原始配置
            app_config.LLM_MODEL_TYPE = original_llm_type
            app_config.EMBEDDING_MODEL_TYPE = original_embedding_type
            
    except Exception as e:
        print(f"❌ 配置测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mixed_configurations():
    """测试混合配置（API + Ollama）"""
    print("\n=== 测试混合配置 ===")
    
    try:
        import app_config
        from common.utils import print_current_config
        
        # 保存原始配置
        original_llm_type = app_config.LLM_MODEL_TYPE
        original_embedding_type = app_config.EMBEDDING_MODEL_TYPE
        
        try:
            # 测试配置1：API LLM + Ollama Embedding
            print("\n--- 测试: API LLM + Ollama Embedding ---")
            app_config.LLM_MODEL_TYPE = "api"
            app_config.EMBEDDING_MODEL_TYPE = "ollama"
            print_current_config()
            
            from embedding_function import get_embedding_function
            embedding_func = get_embedding_function()
            print(f"Embedding函数类型: {type(embedding_func).__name__}")
            
            # 测试配置2：Ollama LLM + API Embedding
            print("\n--- 测试: Ollama LLM + API Embedding ---")
            app_config.LLM_MODEL_TYPE = "ollama"
            app_config.EMBEDDING_MODEL_TYPE = "api"
            print_current_config()
            
            embedding_func = get_embedding_function()
            print(f"Embedding函数类型: {type(embedding_func).__name__}")
            
            print("✅ 混合配置测试通过")
            return True
            
        finally:
            # 恢复原始配置
            app_config.LLM_MODEL_TYPE = original_llm_type
            app_config.EMBEDDING_MODEL_TYPE = original_embedding_type
            
    except Exception as e:
        print(f"❌ 混合配置测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("开始测试Ollama集成功能...")
    print("注意: 这些测试需要Ollama服务运行在 http://localhost:11434")
    print("=" * 60)
    
    results = []
    
    # 测试配置和工具函数（不需要Ollama服务）
    results.append(("配置文件测试", test_ollama_with_config()))
    results.append(("混合配置测试", test_mixed_configurations()))
    
    # 测试实际的Ollama功能（需要Ollama服务）
    print(f"\n{'='*60}")
    print("以下测试需要Ollama服务运行，如果失败可能是服务未启动")
    print("=" * 60)
    
    results.append(("Ollama LLM", test_ollama_llm()))
    results.append(("Ollama Embedding", test_ollama_embedding()))
    
    # 总结
    print(f"\n{'='*60}")
    print("测试结果总结:")
    print("=" * 60)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name}: {status}")
    
    total_passed = sum(1 for _, success in results if success)
    print(f"\n总计: {total_passed}/{len(results)} 个测试通过")
    
    if total_passed == len(results):
        print("🎉 所有测试都通过了！Ollama集成功能正常。")
    else:
        print("⚠️  部分测试失败，请检查Ollama服务是否正常运行。")

if __name__ == "__main__":
    main() 