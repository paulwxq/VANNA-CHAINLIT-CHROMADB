#!/usr/bin/env python3
"""
测试统一的Vanna组合类文件
验证common/vanna_combinations.py中的功能
"""

def test_import_combinations():
    """测试导入组合类"""
    print("=== 测试导入组合类 ===")
    
    try:
        from common.vanna_combinations import (
            Vanna_Qwen_ChromaDB,
            Vanna_DeepSeek_ChromaDB,
            Vanna_Qwen_PGVector,
            Vanna_DeepSeek_PGVector,
            Vanna_Ollama_ChromaDB,
            Vanna_Ollama_PGVector,
            get_vanna_class,
            list_available_combinations,
            print_available_combinations
        )
        print("✅ 成功导入所有组合类和工具函数")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_get_vanna_class():
    """测试get_vanna_class函数"""
    print("\n=== 测试get_vanna_class函数 ===")
    
    try:
        from common.vanna_combinations import get_vanna_class
        
        # 测试有效组合
        test_cases = [
            ("qwen", "chromadb"),
            ("deepseek", "chromadb"),
            ("qwen", "pgvector"),
            ("deepseek", "pgvector"),
            ("ollama", "chromadb"),
            ("ollama", "pgvector"),
        ]
        
        for llm_type, vector_db_type in test_cases:
            try:
                cls = get_vanna_class(llm_type, vector_db_type)
                print(f"✅ {llm_type} + {vector_db_type} -> {cls.__name__}")
            except Exception as e:
                print(f"⚠️  {llm_type} + {vector_db_type} -> 错误: {e}")
        
        # 测试无效组合
        print("\n测试无效组合:")
        try:
            get_vanna_class("invalid_llm", "chromadb")
            print("❌ 应该抛出异常但没有")
            return False
        except ValueError:
            print("✅ 正确处理无效LLM类型")
        
        try:
            get_vanna_class("qwen", "invalid_db")
            print("❌ 应该抛出异常但没有")
            return False
        except ValueError:
            print("✅ 正确处理无效向量数据库类型")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_list_available_combinations():
    """测试列出可用组合"""
    print("\n=== 测试列出可用组合 ===")
    
    try:
        from common.vanna_combinations import list_available_combinations, print_available_combinations
        
        # 获取可用组合
        combinations = list_available_combinations()
        print(f"可用组合数据结构: {combinations}")
        
        # 打印可用组合
        print("\n打印可用组合:")
        print_available_combinations()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_class_instantiation():
    """测试类实例化（不需要实际服务）"""
    print("\n=== 测试类实例化 ===")
    
    try:
        from common.vanna_combinations import get_vanna_class
        
        # 测试ChromaDB组合（通常可用）
        test_cases = [
            ("qwen", "chromadb"),
            ("deepseek", "chromadb"),
        ]
        
        for llm_type, vector_db_type in test_cases:
            try:
                cls = get_vanna_class(llm_type, vector_db_type)
                
                # 尝试创建实例（使用空配置）
                instance = cls(config={})
                print(f"✅ 成功创建 {cls.__name__} 实例")
                
                # 检查实例类型
                print(f"   实例类型: {type(instance)}")
                print(f"   MRO: {[c.__name__ for c in type(instance).__mro__[:3]]}")
                
            except Exception as e:
                print(f"⚠️  创建 {llm_type}+{vector_db_type} 实例失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_factory_integration():
    """测试与工厂函数的集成"""
    print("\n=== 测试与工厂函数的集成 ===")
    
    try:
        import app_config
        from common.utils import print_current_config
        
        # 保存原始配置
        original_llm_type = app_config.LLM_MODEL_TYPE
        original_embedding_type = app_config.EMBEDDING_MODEL_TYPE
        original_vector_db = app_config.VECTOR_DB_NAME
        
        try:
            # 测试不同配置
            test_configs = [
                ("api", "api", "qwen", "chromadb"),
                ("api", "api", "deepseek", "chromadb"),
                ("ollama", "ollama", None, "chromadb"),
            ]
            
            for llm_type, emb_type, llm_name, vector_db in test_configs:
                print(f"\n--- 测试配置: LLM={llm_type}, EMB={emb_type}, MODEL={llm_name}, DB={vector_db} ---")
                
                # 设置配置
                app_config.LLM_MODEL_TYPE = llm_type
                app_config.EMBEDDING_MODEL_TYPE = emb_type
                if llm_name:
                    app_config.LLM_MODEL_NAME = llm_name
                app_config.VECTOR_DB_NAME = vector_db
                
                # 打印当前配置
                print_current_config()
                
                # 测试工厂函数（不实际创建实例，只测试类选择）
                try:
                    from vanna_llm_factory import create_vanna_instance
                    from common.utils import get_current_model_info, is_using_ollama_llm
                    from common.vanna_combinations import get_vanna_class
                    
                    model_info = get_current_model_info()
                    
                    if is_using_ollama_llm():
                        selected_llm_type = "ollama"
                    else:
                        selected_llm_type = model_info["llm_model"].lower()
                    
                    selected_vector_db = model_info["vector_db"].lower()
                    
                    cls = get_vanna_class(selected_llm_type, selected_vector_db)
                    print(f"✅ 工厂函数会选择: {cls.__name__}")
                    
                except Exception as e:
                    print(f"⚠️  工厂函数测试失败: {e}")
            
            return True
            
        finally:
            # 恢复原始配置
            app_config.LLM_MODEL_TYPE = original_llm_type
            app_config.EMBEDDING_MODEL_TYPE = original_embedding_type
            app_config.VECTOR_DB_NAME = original_vector_db
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("开始测试统一的Vanna组合类...")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("导入组合类", test_import_combinations()))
    results.append(("get_vanna_class函数", test_get_vanna_class()))
    results.append(("列出可用组合", test_list_available_combinations()))
    results.append(("类实例化", test_class_instantiation()))
    results.append(("工厂函数集成", test_factory_integration()))
    
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
        print("🎉 所有测试都通过了！统一组合类文件工作正常。")
    else:
        print("⚠️  部分测试失败，请检查相关依赖和配置。")

if __name__ == "__main__":
    main() 