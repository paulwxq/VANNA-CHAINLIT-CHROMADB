"""
测试 Vanna 单例模式是否正常工作
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_vanna_singleton():
    """测试 Vanna 单例模式"""
    from common.vanna_instance import get_vanna_instance, get_instance_status
    
    print("=" * 50)
    print("测试 Vanna 单例模式")
    print("=" * 50)
    
    # 检查初始状态
    status = get_instance_status()
    print(f"初始状态: {status}")
    
    # 第一次获取实例
    print("\n第一次获取实例...")
    instance1 = get_vanna_instance()
    print(f"实例1 ID: {id(instance1)}")
    print(f"实例1 类型: {type(instance1)}")
    
    # 第二次获取实例（应该是同一个）
    print("\n第二次获取实例...")
    instance2 = get_vanna_instance()
    print(f"实例2 ID: {id(instance2)}")
    print(f"实例2 类型: {type(instance2)}")
    
    # 验证是否为同一个实例
    is_same = instance1 is instance2
    print(f"\n实例是否相同: {is_same}")
    
    # 检查最终状态
    final_status = get_instance_status()
    print(f"最终状态: {final_status}")
    
    if is_same:
        print("\n✅ 单例模式测试通过！")
    else:
        print("\n❌ 单例模式测试失败！")
    
    return is_same

def test_import_from_tools():
    """测试从工具文件导入是否正常"""
    print("\n" + "=" * 50)
    print("测试从工具文件导入")
    print("=" * 50)
    
    try:
        # 导入工具模块
        from agent.tools.sql_generation import get_vanna_instance as gen_instance
        from agent.tools.sql_execution import get_vanna_instance as exec_instance
        from agent.tools.summary_generation import get_vanna_instance as sum_instance
        
        # 获取实例
        instance_gen = gen_instance()
        instance_exec = exec_instance()
        instance_sum = sum_instance()
        
        print(f"SQL生成工具实例 ID: {id(instance_gen)}")
        print(f"SQL执行工具实例 ID: {id(instance_exec)}")
        print(f"摘要生成工具实例 ID: {id(instance_sum)}")
        
        # 验证是否都是同一个实例
        all_same = (instance_gen is instance_exec) and (instance_exec is instance_sum)
        
        if all_same:
            print("\n✅ 工具导入测试通过！所有工具使用同一个实例")
        else:
            print("\n❌ 工具导入测试失败！工具使用不同的实例")
        
        return all_same
        
    except Exception as e:
        print(f"\n❌ 导入测试异常: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        singleton_test = test_vanna_singleton()
        import_test = test_import_from_tools()
        
        print("\n" + "=" * 50)
        print("测试总结")
        print("=" * 50)
        print(f"单例模式测试: {'通过' if singleton_test else '失败'}")
        print(f"工具导入测试: {'通过' if import_test else '失败'}")
        
        if singleton_test and import_test:
            print("\n🎉 所有测试通过！Vanna 单例模式工作正常")
        else:
            print("\n⚠️  存在测试失败，请检查实现")
            
    except Exception as e:
        print(f"测试执行异常: {str(e)}")
        import traceback
        traceback.print_exc() 