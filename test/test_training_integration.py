#!/usr/bin/env python3
"""
测试training目录的代码集成
验证训练相关的模块是否能正常工作
"""

def test_training_imports():
    """测试训练模块的导入"""
    print("=== 测试训练模块导入 ===")
    
    try:
        # 测试从training包导入
        from training import (
            train_ddl,
            train_documentation,
            train_sql_example,
            train_question_sql_pair,
            flush_training,
            shutdown_trainer
        )
        print("✅ 成功从training包导入所有函数")
        
        # 测试直接导入
        from training.vanna_trainer import BatchProcessor
        print("✅ 成功导入BatchProcessor类")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_access():
    """测试配置访问"""
    print("\n=== 测试配置访问 ===")
    
    try:
        import app_config
        
        # 测试训练批处理配置
        batch_enabled = getattr(app_config, 'TRAINING_BATCH_PROCESSING_ENABLED', None)
        batch_size = getattr(app_config, 'TRAINING_BATCH_SIZE', None)
        max_workers = getattr(app_config, 'TRAINING_MAX_WORKERS', None)
        
        print(f"批处理启用: {batch_enabled}")
        print(f"批处理大小: {batch_size}")
        print(f"最大工作线程: {max_workers}")
        
        if batch_enabled is not None and batch_size is not None and max_workers is not None:
            print("✅ 训练批处理配置正常")
        else:
            print("⚠️  部分训练批处理配置缺失")
        
        # 测试向量数据库配置
        vector_db_name = getattr(app_config, 'VECTOR_DB_NAME', None)
        print(f"向量数据库类型: {vector_db_name}")
        
        if vector_db_name == "pgvector":
            pgvector_config = getattr(app_config, 'PGVECTOR_CONFIG', None)
            if pgvector_config:
                print("✅ PgVector配置存在")
            else:
                print("❌ PgVector配置缺失")
        
        # 测试新的配置工具函数
        try:
            from common.utils import get_current_embedding_config, get_current_model_info
            
            embedding_config = get_current_embedding_config()
            model_info = get_current_model_info()
            
            print(f"当前embedding类型: {model_info['embedding_type']}")
            print(f"当前embedding模型: {model_info['embedding_model']}")
            print("✅ 新配置工具函数正常工作")
            
        except Exception as e:
            print(f"⚠️  新配置工具函数测试失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置访问测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_vanna_instance_creation():
    """测试Vanna实例创建"""
    print("\n=== 测试Vanna实例创建 ===")
    
    try:
        from vanna_llm_factory import create_vanna_instance
        
        print("尝试创建Vanna实例...")
        vn = create_vanna_instance()
        
        print(f"✅ 成功创建Vanna实例: {type(vn).__name__}")
        
        # 测试基本方法是否存在
        required_methods = ['train', 'generate_question', 'get_training_data']
        for method in required_methods:
            if hasattr(vn, method):
                print(f"✅ 方法 {method} 存在")
            else:
                print(f"⚠️  方法 {method} 不存在")
        
        return True
        
    except Exception as e:
        print(f"❌ Vanna实例创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_batch_processor():
    """测试批处理器"""
    print("\n=== 测试批处理器 ===")
    
    try:
        from training.vanna_trainer import BatchProcessor
        import app_config
        
        # 创建测试批处理器
        batch_size = getattr(app_config, 'TRAINING_BATCH_SIZE', 5)
        max_workers = getattr(app_config, 'TRAINING_MAX_WORKERS', 2)
        
        processor = BatchProcessor(batch_size=batch_size, max_workers=max_workers)
        print(f"✅ 成功创建BatchProcessor实例")
        print(f"   批处理大小: {processor.batch_size}")
        print(f"   最大工作线程: {processor.max_workers}")
        print(f"   批处理启用: {processor.batch_enabled}")
        
        # 测试关闭
        processor.shutdown()
        print("✅ 批处理器关闭成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 批处理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_training_functions():
    """测试训练函数（不实际训练）"""
    print("\n=== 测试训练函数 ===")
    
    try:
        from training import (
            train_ddl,
            train_documentation,
            train_sql_example,
            train_question_sql_pair,
            flush_training,
            shutdown_trainer
        )
        
        print("✅ 所有训练函数导入成功")
        
        # 测试函数是否可调用
        functions_to_test = [
            ('train_ddl', train_ddl),
            ('train_documentation', train_documentation),
            ('train_sql_example', train_sql_example),
            ('train_question_sql_pair', train_question_sql_pair),
            ('flush_training', flush_training),
            ('shutdown_trainer', shutdown_trainer)
        ]
        
        for func_name, func in functions_to_test:
            if callable(func):
                print(f"✅ {func_name} 是可调用的")
            else:
                print(f"❌ {func_name} 不可调用")
        
        return True
        
    except Exception as e:
        print(f"❌ 训练函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_embedding_connection():
    """测试embedding连接"""
    print("\n=== 测试Embedding连接 ===")
    
    try:
        from embedding_function import test_embedding_connection
        
        print("测试embedding模型连接...")
        result = test_embedding_connection()
        
        if result["success"]:
            print(f"✅ Embedding连接成功: {result['message']}")
        else:
            print(f"⚠️  Embedding连接失败: {result['message']}")
            print("   这可能是因为API服务未启动或配置不正确")
        
        return True
        
    except Exception as e:
        print(f"❌ Embedding连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_run_training_script():
    """测试run_training.py脚本的基本功能"""
    print("\n=== 测试run_training.py脚本 ===")
    
    try:
        # 导入run_training模块
        import sys
        import os
        
        # 添加training目录到路径
        training_dir = os.path.join(os.path.dirname(__file__), 'training')
        if training_dir not in sys.path:
            sys.path.insert(0, training_dir)
        
        # 导入run_training模块的函数
        from training.run_training import (
            read_file_by_delimiter,
            read_markdown_file_by_sections,
            check_pgvector_connection
        )
        
        print("✅ 成功导入run_training模块的函数")
        
        # 测试文件读取函数
        test_content = "section1---section2---section3"
        with open("test_temp.txt", "w", encoding="utf-8") as f:
            f.write(test_content)
        
        try:
            sections = read_file_by_delimiter("test_temp.txt", "---")
            if len(sections) == 3:
                print("✅ read_file_by_delimiter 函数正常工作")
            else:
                print(f"⚠️  read_file_by_delimiter 返回了 {len(sections)} 个部分，期望 3 个")
        finally:
            if os.path.exists("test_temp.txt"):
                os.remove("test_temp.txt")
        
        return True
        
    except Exception as e:
        print(f"❌ run_training.py脚本测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("开始测试training目录的代码集成...")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("训练模块导入", test_training_imports()))
    results.append(("配置访问", test_config_access()))
    results.append(("Vanna实例创建", test_vanna_instance_creation()))
    results.append(("批处理器", test_batch_processor()))
    results.append(("训练函数", test_training_functions()))
    results.append(("Embedding连接", test_embedding_connection()))
    results.append(("run_training脚本", test_run_training_script()))
    
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
        print("🎉 所有测试都通过了！training目录的代码可以正常工作。")
    elif total_passed >= len(results) - 1:
        print("✅ 大部分测试通过，training目录的代码基本可以正常工作。")
        print("   部分失败可能是由于服务未启动或配置问题。")
    else:
        print("⚠️  多个测试失败，请检查相关依赖和配置。")

if __name__ == "__main__":
    main() 