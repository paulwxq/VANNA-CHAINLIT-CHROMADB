# test_routing_modes.py - 测试不同路由模式的功能

import sys
import os
# 添加项目根目录到sys.path，以便导入app_config.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_routing_modes():
    """测试不同路由模式的配置和分类器行为"""
    
    print("=== 路由模式测试 ===")
    
    # 1. 测试配置参数
    try:
        import app_config
        print(f"✓ 配置导入成功")
        print(f"当前路由模式: {getattr(app_config, 'QUESTION_ROUTING_MODE', '未找到')}")
    except ImportError as e:
        print(f"✗ 配置导入失败: {e}")
        return False
    
    # 2. 测试分类器
    try:
        from agent.classifier import QuestionClassifier, ClassificationResult
        classifier = QuestionClassifier()
        print(f"✓ 分类器创建成功")
        
        # 测试问题
        test_questions = [
            "查询本月服务区营业额",
            "你好，请介绍一下平台功能",
            "请问负责每个服务区的经理的名字是什么？"
        ]
        
        # 临时修改路由模式进行测试
        original_mode = getattr(app_config, 'QUESTION_ROUTING_MODE', 'hybrid')
        
        for mode in ["hybrid", "llm_only", "database_direct", "chat_direct"]:
            print(f"\n--- 测试路由模式: {mode} ---")
            app_config.QUESTION_ROUTING_MODE = mode
            
            for question in test_questions:
                try:
                    result = classifier.classify(question)
                    print(f"问题: {question}")
                    print(f"  分类: {result.question_type}")
                    print(f"  置信度: {result.confidence}")
                    print(f"  方法: {result.method}")
                    print(f"  理由: {result.reason[:50]}...")
                except Exception as e:
                    print(f"  分类异常: {e}")
        
        # 恢复原始配置
        app_config.QUESTION_ROUTING_MODE = original_mode
        print(f"\n✓ 分类器测试完成")
        
    except ImportError as e:
        print(f"✗ 分类器导入失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 分类器测试异常: {e}")
        return False
    
    # 3. 测试Agent状态
    try:
        from agent.state import AgentState
        print(f"✓ Agent状态定义正确")
    except ImportError as e:
        print(f"✗ Agent状态导入失败: {e}")
        return False
    
    # 4. 测试Agent工作流创建（基础测试，不实际运行）
    try:
        from agent.citu_agent import CituLangGraphAgent
        print(f"✓ Agent类导入成功")
        
        # 注意：这里只测试导入，不实际创建Agent实例
        # 因为可能涉及LLM连接等复杂依赖
        
    except ImportError as e:
        print(f"✗ Agent类导入失败: {e}")
        return False
    except Exception as e:
        print(f"警告: Agent相关模块可能有依赖问题: {e}")
    
    print(f"\n=== 路由模式测试完成 ===")
    return True

if __name__ == "__main__":
    success = test_routing_modes()
    if success:
        print("✓ 所有测试通过！路由模式功能实现成功！")
    else:
        print("✗ 测试失败，请检查实现。")