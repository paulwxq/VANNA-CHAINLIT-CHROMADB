#!/usr/bin/env python3
"""
Data Pipeline 独立任务执行器

专门用于subprocess调用，执行data pipeline任务
"""

import sys
import asyncio
import argparse
import json
from pathlib import Path

# 确保能够导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_pipeline.api.simple_workflow import SimpleWorkflowExecutor
from core.logging import initialize_logging


def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(description='Data Pipeline 任务执行器')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--execution-mode', default='complete', choices=['complete', 'step'], help='执行模式')
    parser.add_argument('--step-name', help='步骤名称（当execution-mode=step时必需）')
    
    args = parser.parse_args()
    
    # 初始化日志系统
    initialize_logging()
    
    # 验证参数
    if args.execution_mode == 'step' and not args.step_name:
        print("错误: 步骤执行模式需要指定--step-name参数", file=sys.stderr)
        sys.exit(1)
    
    try:
        # 执行任务
        result = asyncio.run(execute_task(args.task_id, args.execution_mode, args.step_name))
        
        # 输出结果到stdout（供父进程读取）
        print(json.dumps(result, ensure_ascii=False, default=str))
        
        # 设置退出码
        sys.exit(0 if result.get('success', False) else 1)
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "task_id": args.task_id,
            "execution_mode": args.execution_mode
        }
        print(json.dumps(error_result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


async def execute_task(task_id: str, execution_mode: str, step_name: str = None):
    """执行任务的异步函数"""
    executor = None
    try:
        executor = SimpleWorkflowExecutor(task_id)
        
        if execution_mode == "complete":
            return await executor.execute_complete_workflow()
        elif execution_mode == "step":
            return await executor.execute_single_step(step_name)
        else:
            raise ValueError(f"不支持的执行模式: {execution_mode}")
            
    finally:
        if executor:
            executor.cleanup()


if __name__ == "__main__":
    main()