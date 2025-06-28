#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日志系统测试脚本
用于验证日志服务改造是否成功
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_logging_system():
    """测试日志系统的各个功能"""
    print("=" * 60)
    print("开始测试日志系统...")
    print("=" * 60)
    
    # 1. 测试日志系统初始化
    try:
        from core.logging import initialize_logging, get_app_logger, get_agent_logger, get_vanna_logger, get_data_pipeline_logger
        from core.logging import set_log_context, clear_log_context
        
        # 初始化日志系统
        initialize_logging()
        print("✅ 日志系统初始化成功")
    except Exception as e:
        print(f"❌ 日志系统初始化失败: {e}")
        return
    
    # 2. 测试各模块的logger
    print("\n测试各模块的logger...")
    
    # App模块
    try:
        app_logger = get_app_logger("TestApp")
        app_logger.info("这是App模块的测试日志")
        app_logger.warning("这是App模块的警告日志")
        app_logger.error("这是App模块的错误日志")
        print("✅ App模块logger测试成功")
    except Exception as e:
        print(f"❌ App模块logger测试失败: {e}")
    
    # Agent模块
    try:
        agent_logger = get_agent_logger("TestAgent")
        agent_logger.info("这是Agent模块的测试日志")
        agent_logger.debug("这是Agent模块的调试日志")
        print("✅ Agent模块logger测试成功")
    except Exception as e:
        print(f"❌ Agent模块logger测试失败: {e}")
    
    # Vanna模块
    try:
        vanna_logger = get_vanna_logger("TestVanna")
        vanna_logger.info("这是Vanna模块的测试日志")
        vanna_logger.warning("这是Vanna模块的警告日志")
        print("✅ Vanna模块logger测试成功")
    except Exception as e:
        print(f"❌ Vanna模块logger测试失败: {e}")
    
    # Data Pipeline模块
    try:
        dp_logger = get_data_pipeline_logger("TestDataPipeline")
        dp_logger.info("这是Data Pipeline模块的测试日志")
        dp_logger.error("这是Data Pipeline模块的错误日志")
        print("✅ Data Pipeline模块logger测试成功")
    except Exception as e:
        print(f"❌ Data Pipeline模块logger测试失败: {e}")
    
    # 3. 测试上下文功能
    print("\n测试上下文功能...")
    try:
        # 设置上下文
        set_log_context(user_id="test_user_123", session_id="session_456")
        app_logger.info("这是带上下文的日志")
        
        # 清除上下文
        clear_log_context()
        app_logger.info("这是清除上下文后的日志")
        print("✅ 上下文功能测试成功")
    except Exception as e:
        print(f"❌ 上下文功能测试失败: {e}")
    
    # 4. 检查日志文件
    print("\n检查日志文件...")
    log_dir = Path("logs")
    expected_files = ["app.log", "agent.log", "vanna.log", "data_pipeline.log"]
    
    if log_dir.exists():
        print(f"日志目录: {log_dir.absolute()}")
        for log_file in expected_files:
            file_path = log_dir / log_file
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"✅ {log_file} - 大小: {size} bytes")
                
                # 显示最后几行日志
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if lines:
                            print(f"   最新日志: {lines[-1].strip()}")
                except Exception as e:
                    print(f"   读取日志失败: {e}")
            else:
                print(f"❌ {log_file} - 文件不存在")
    else:
        print(f"❌ 日志目录不存在: {log_dir}")
    
    print("\n" + "=" * 60)
    print("日志系统测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_logging_system() 