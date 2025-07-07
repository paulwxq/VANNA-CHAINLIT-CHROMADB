#!/usr/bin/env python3
"""
测试thinking内容控制功能
验证DISPLAY_RESULT_THINKING参数是否正确控制thinking内容的显示/隐藏
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_thinking_removal():
    """测试thinking内容移除功能"""
    from customllm.base_llm_chat import BaseLLMChat
    
    # 创建一个测试类来测试_remove_thinking_content方法
    class TestLLM(BaseLLMChat):
        def submit_prompt(self, prompt, **kwargs):
            return "测试响应"
    
    # 创建测试实例
    test_llm = TestLLM(config={})
    
    # 测试用例
    test_cases = [
        # 基本thinking标签
        {
            "input": "<think>这是思考内容</think>这是最终答案",
            "expected": "这是最终答案"
        },
        # 多行thinking标签
        {
            "input": "<think>\n这是多行\n思考内容\n</think>\n\n这是最终答案",
            "expected": "这是最终答案"
        },
        # 大小写不敏感
        {
            "input": "<THINK>大写思考</THINK>最终答案",
            "expected": "最终答案"
        },
        # 多个thinking标签
        {
            "input": "<think>第一段思考</think>中间内容<think>第二段思考</think>最终答案",
            "expected": "中间内容最终答案"
        },
        # 没有thinking标签
        {
            "input": "这是没有thinking标签的普通文本",
            "expected": "这是没有thinking标签的普通文本"
        },
        # 空文本
        {
            "input": "",
            "expected": ""
        },
        # None输入
        {
            "input": None,
            "expected": None
        }
    ]
    
    print("=== 测试thinking内容移除功能 ===")
    
    for i, test_case in enumerate(test_cases, 1):
        input_text = test_case["input"]
        expected = test_case["expected"]
        
        result = test_llm._remove_thinking_content(input_text)
        
        if result == expected:
            print(f"✅ 测试用例 {i}: 通过")
        else:
            print(f"❌ 测试用例 {i}: 失败")
            print(f"   输入: {repr(input_text)}")
            print(f"   期望: {repr(expected)}")
            print(f"   实际: {repr(result)}")
    
    print()

def test_config_integration():
    """测试配置集成"""
    print("=== 测试配置集成 ===")
    
    try:
        from app_config import DISPLAY_RESULT_THINKING
        print(f"✅ 成功导入配置: DISPLAY_RESULT_THINKING = {DISPLAY_RESULT_THINKING}")
        
        from customllm.base_llm_chat import BaseLLMChat
        print("✅ 成功导入BaseLLMChat类")
        
        # 检查类中是否正确导入了配置
        import customllm.base_llm_chat as base_module
        if hasattr(base_module, 'DISPLAY_RESULT_THINKING'):
            print(f"✅ BaseLLMChat模块中的配置: DISPLAY_RESULT_THINKING = {base_module.DISPLAY_RESULT_THINKING}")
        else:
            print("❌ BaseLLMChat模块中未找到DISPLAY_RESULT_THINKING配置")
            
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
    
    print()

def test_vanna_instance():
    """测试Vanna实例的thinking处理"""
    print("=== 测试Vanna实例thinking处理 ===")
    
    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        
        print(f"✅ 成功获取Vanna实例: {type(vn).__name__}")
        
        # 检查实例是否有_remove_thinking_content方法
        if hasattr(vn, '_remove_thinking_content'):
            print("✅ Vanna实例具有_remove_thinking_content方法")
            
            # 测试方法
            test_text = "<think>测试思考</think>测试结果"
            cleaned = vn._remove_thinking_content(test_text)
            if cleaned == "测试结果":
                print("✅ thinking内容移除功能正常工作")
            else:
                print(f"❌ thinking内容移除异常: {repr(cleaned)}")
        else:
            print("❌ Vanna实例缺少_remove_thinking_content方法")
            
    except Exception as e:
        print(f"❌ 测试Vanna实例失败: {e}")
    
    print()

def main():
    """主测试函数"""
    print("开始测试thinking内容控制功能...\n")
    
    # 运行所有测试
    test_thinking_removal()
    test_config_integration()
    test_vanna_instance()
    
    print("测试完成！")

if __name__ == "__main__":
    main() 