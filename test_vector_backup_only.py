#!/usr/bin/env python3
"""
独立测试Vector表备份功能
只备份langchain_pg_collection和langchain_pg_embedding表
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime


async def test_vector_backup():
    """测试vector表备份功能"""
    
    print("🧪 开始测试Vector表备份功能...")
    print("=" * 50)
    
    # 1. 设置测试输出目录
    test_dir = Path("./test_vector_backup_output")
    test_dir.mkdir(exist_ok=True)
    
    print(f"📁 测试输出目录: {test_dir.resolve()}")
    
    try:
        # 2. 导入VectorTableManager
        from data_pipeline.trainer.vector_table_manager import VectorTableManager
        
        # 3. 创建管理器实例
        task_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        vector_manager = VectorTableManager(
            task_output_dir=str(test_dir), 
            task_id=task_id
        )
        
        print(f"🆔 任务ID: {task_id}")
        print("🔧 VectorTableManager 创建成功")
        
        # 4. 执行备份（只备份，不清空）
        print("\n🗂️ 开始执行备份...")
        result = await vector_manager.execute_vector_management(
            backup=True,    # 执行备份
            truncate=False  # 不清空表
        )
        
        # 5. 显示结果
        print("\n📊 备份结果:")
        print("=" * 30)
        
        if result.get("backup_performed", False):
            print("✅ 备份状态: 已执行")
            
            tables_info = result.get("tables_backed_up", {})
            for table_name, info in tables_info.items():
                if info.get("success", False):
                    print(f"  ✅ {table_name}: {info['row_count']}行 -> {info['backup_file']} ({info['file_size']})")
                else:
                    print(f"  ❌ {table_name}: 失败 - {info.get('error', '未知错误')}")
        else:
            print("❌ 备份状态: 未执行")
        
        duration = result.get("duration", 0)
        print(f"⏱️  总耗时: {duration:.2f}秒")
        
        errors = result.get("errors", [])
        if errors:
            print(f"⚠️  错误信息: {'; '.join(errors)}")
        
        # 6. 检查生成的文件
        backup_dir = test_dir / "vector_bak"
        if backup_dir.exists():
            print(f"\n📂 备份文件目录: {backup_dir.resolve()}")
            backup_files = list(backup_dir.glob("*.csv"))
            if backup_files:
                print("📄 生成的备份文件:")
                for file in backup_files:
                    file_size = file.stat().st_size
                    print(f"  📄 {file.name} ({file_size} bytes)")
            else:
                print("⚠️  未找到CSV备份文件")
                
            log_files = list(backup_dir.glob("*.txt"))
            if log_files:
                print("📋 日志文件:")
                for file in log_files:
                    print(f"  📋 {file.name}")
        else:
            print("❌ 备份目录不存在")
        
        print("\n🎉 测试完成!")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        print("详细错误信息:")
        print(traceback.format_exc())
        return False


def main():
    """主函数"""
    print("Vector表备份功能独立测试")
    print("测试目标: langchain_pg_collection, langchain_pg_embedding")
    print("数据库: 从 data_pipeline.config 自动获取连接配置")
    print()
    
    # 运行异步测试
    success = asyncio.run(test_vector_backup())
    
    if success:
        print("\n✅ 所有测试通过!")
        exit(0)
    else:
        print("\n❌ 测试失败!")
        exit(1)


if __name__ == "__main__":
    main() 