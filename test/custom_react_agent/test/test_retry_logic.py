"""
测试修复后的重试逻辑
"""
import asyncio
import sys
import os

# 添加路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

import config

def test_error_classification():
    """测试错误分类逻辑"""
    print("🧪 测试错误分类逻辑")
    
    # 测试用例
    test_cases = [
        ("Request timed out.", True, "应该识别为网络错误"),
        ("APITimeoutError: timeout", True, "应该识别为网络错误"),
        ("Connection error occurred", True, "应该识别为网络错误"),
        ("ReadTimeout exception", True, "应该识别为网络错误"),
        ("ValueError: invalid input", False, "应该识别为非网络错误"),
        ("KeyError: missing key", False, "应该识别为非网络错误"),
    ]
    
    # 网络错误关键词（与agent.py中一致）
    network_keywords = [
        "Connection error", "APIConnectionError", "ConnectError", 
        "timeout", "timed out", "TimeoutError", "APITimeoutError",
        "ReadTimeout", "ConnectTimeout", "远程主机强迫关闭", "网络连接"
    ]
    
    for error_msg, expected, description in test_cases:
        is_network_error = any(keyword in error_msg for keyword in network_keywords)
        status = "✅" if is_network_error == expected else "❌"
        print(f"   {status} {description}")
        print(f"      错误信息: '{error_msg}'")
        print(f"      预期: {'网络错误' if expected else '非网络错误'}")
        print(f"      实际: {'网络错误' if is_network_error else '非网络错误'}")
        print()

def test_retry_intervals():
    """测试重试间隔计算"""
    print("⏱️  测试重试间隔计算")
    
    base_delay = config.RETRY_BASE_DELAY  # 2秒
    max_retries = config.MAX_RETRIES      # 5次
    
    print(f"   基础延迟: {base_delay}秒")
    print(f"   最大重试: {max_retries}次")
    print()
    
    total_wait_time = 0
    for attempt in range(max_retries - 1):  # 不包括最后一次（不会重试）
        # 新的计算公式：wait_time = base_delay * (2 ** attempt) + attempt
        wait_time = base_delay * (2 ** attempt) + attempt
        total_wait_time += wait_time
        print(f"   第{attempt + 1}次失败后等待: {wait_time}秒")
    
    print(f"\n   总等待时间: {total_wait_time}秒")
    print(f"   加上LLM超时({config.NETWORK_TIMEOUT}秒 x {max_retries}次): {config.NETWORK_TIMEOUT * max_retries}秒")
    print(f"   最大总耗时: {total_wait_time + config.NETWORK_TIMEOUT * max_retries}秒")

if __name__ == "__main__":
    print("🔧 测试修复后的重试机制\n")
    test_error_classification()
    print("=" * 50)
    test_retry_intervals()
    print("\n✅ 测试完成")