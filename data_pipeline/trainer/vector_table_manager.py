import asyncio
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import psycopg2
import logging


class VectorTableManager:
    """Vector表管理器，负责备份和清空操作"""
    
    def __init__(self, task_output_dir: str, task_id: str = None):
        """
        Args:
            task_output_dir: 任务输出目录（用于存放备份文件）
            task_id: 任务ID（用于日志记录）
        Note:
            数据库连接将从data_pipeline.config.SCHEMA_TOOLS_CONFIG自动获取
        """
        self.task_output_dir = task_output_dir
        self.task_id = task_id
        
        # 从data_pipeline.config获取配置
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        self.config = SCHEMA_TOOLS_CONFIG.get("vector_table_management", {})
        
        # 初始化日志
        if task_id:
            from data_pipeline.dp_logging import get_logger
            self.logger = get_logger("VectorTableManager", task_id)
        else:
            import logging
            self.logger = logging.getLogger("VectorTableManager")
    
    async def execute_vector_management(self, backup: bool, truncate: bool) -> Dict[str, Any]:
        """执行vector表管理操作的主流程"""
        
        start_time = time.time()
        
        # 1. 参数验证和自动启用逻辑
        if truncate and not backup:
            backup = True
            self.logger.info("🔄 启用truncate时自动启用backup")
        
        if not backup and not truncate:
            self.logger.info("⏭️ 未启用vector表管理，跳过操作")
            return {"backup_performed": False, "truncate_performed": False}
        
        # 2. 初始化结果统计
        result = {
            "backup_performed": backup,
            "truncate_performed": truncate,
            "tables_backed_up": {},
            "truncate_results": {},
            "errors": [],
            "backup_directory": None,
            "duration": 0
        }
        
        try:
            # 3. 创建备份目录
            backup_dir = Path(self.task_output_dir) / self.config.get("backup_directory", "vector_bak")
            if backup:
                backup_dir.mkdir(parents=True, exist_ok=True)
                result["backup_directory"] = str(backup_dir)
                self.logger.info(f"📁 备份目录: {backup_dir}")
            
            # 4. 执行备份操作
            if backup:
                self.logger.info("🗂️ 开始备份vector表...")
                backup_results = await self.backup_vector_tables()
                result["tables_backed_up"] = backup_results
                
                # 检查备份是否全部成功
                backup_failed = any(not r.get("success", False) for r in backup_results.values())
                if backup_failed:
                    result["errors"].append("部分表备份失败")
                    if truncate:
                        self.logger.error("❌ 备份失败，取消清空操作")
                        result["truncate_performed"] = False
                        truncate = False
            
            # 5. 执行清空操作（仅在备份成功时）
            if truncate:
                self.logger.info("🗑️ 开始清空vector表...")
                truncate_results = await self.truncate_vector_tables()
                result["truncate_results"] = truncate_results
                
                # 检查清空是否成功
                truncate_failed = any(not r.get("success", False) for r in truncate_results.values())
                if truncate_failed:
                    result["errors"].append("部分表清空失败")
            
            # 6. 生成备份日志文件
            if backup and backup_dir.exists():
                self._write_backup_log(backup_dir, result)
            
            # 7. 计算总耗时
            result["duration"] = time.time() - start_time
            
            # 8. 记录最终状态
            if result["errors"]:
                self.logger.warning(f"⚠️ Vector表管理完成，但有错误: {'; '.join(result['errors'])}")
            else:
                self.logger.info(f"✅ Vector表管理完成，耗时: {result['duration']:.2f}秒")
            
            return result
            
        except Exception as e:
            result["duration"] = time.time() - start_time
            result["errors"].append(f"执行失败: {str(e)}")
            self.logger.error(f"❌ Vector表管理失败: {e}")
            raise
    
    async def backup_vector_tables(self) -> Dict[str, Any]:
        """备份vector表数据"""
        
        # 1. 创建备份目录
        backup_dir = Path(self.task_output_dir) / self.config.get("backup_directory", "vector_bak")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. 生成时间戳
        timestamp = datetime.now().strftime(self.config.get("timestamp_format", "%Y%m%d_%H%M%S"))
        
        # 3. 执行备份（每个表分别处理）
        results = {}
        supported_tables = self.config.get("supported_tables", ["langchain_pg_collection", "langchain_pg_embedding"])
        
        for table_name in supported_tables:
            try:
                # 3.1 定义文件路径（.tmp临时文件）
                temp_file = backup_dir / f"{table_name}_{timestamp}.csv.tmp"
                final_file = backup_dir / f"{table_name}_{timestamp}.csv"
                
                # 确保使用绝对路径（PostgreSQL COPY命令要求）
                temp_file_abs = temp_file.resolve()
                
                # 3.2 通过psycopg2使用流式客户端导出（支持大数据量）
                start_time = time.time()
                row_count = 0
                batch_size = 10000  # 每批处理1万条记录
                
                with self.get_connection() as conn:
                    # 临时关闭autocommit以支持流式处理
                    old_autocommit = conn.autocommit
                    conn.autocommit = False
                    
                    try:
                        with conn.cursor() as cursor:
                            # 设置游标为流式模式
                            cursor.itersize = batch_size
                            
                            # 执行编码设置
                            cursor.execute("SET client_encoding TO 'UTF8'")
                            
                            # 执行查询
                            cursor.execute(f"SELECT * FROM {table_name}")
                            
                            # 获取列名
                            colnames = [desc[0] for desc in cursor.description]
                            
                            # 使用流式方式写入CSV文件
                            import csv
                            with open(temp_file_abs, 'w', newline='', encoding='utf-8') as csvfile:
                                writer = csv.writer(csvfile)
                                
                                # 写入表头
                                writer.writerow(colnames)
                                
                                # 流式读取和写入数据
                                while True:
                                    rows = cursor.fetchmany(batch_size)
                                    if not rows:
                                        break
                                        
                                    # 批量写入当前批次的数据
                                    for row in rows:
                                        writer.writerow(row)
                                        row_count += 1
                                    
                                    # 记录进度（大数据量时有用）
                                    if row_count % (batch_size * 5) == 0:  # 每5万条记录记录一次
                                        self.logger.info(f"📊 {table_name} 已导出 {row_count} 行数据...")
                        
                        # 提交事务
                        conn.commit()
                        
                    finally:
                        # 恢复原来的autocommit设置
                        conn.autocommit = old_autocommit
                
                self.logger.info(f"📊 {table_name} 流式导出完成，总计 {row_count} 行")
                
                # 3.3 导出完成后，重命名文件 (.tmp -> .csv)
                if temp_file.exists():
                    temp_file.rename(final_file)
                    
                    # 3.4 获取文件信息
                    file_stat = final_file.stat()
                    duration = time.time() - start_time
                    
                    results[table_name] = {
                        "success": True,
                        "row_count": row_count,
                        "file_size": self._format_file_size(file_stat.st_size),
                        "backup_file": final_file.name,
                        "duration": duration
                    }
                    
                    self.logger.info(f"✅ {table_name} 备份成功: {row_count}行 -> {final_file.name}")
                else:
                    raise Exception(f"临时文件 {temp_file} 未生成")
                    
            except Exception as e:
                results[table_name] = {
                    "success": False,
                    "error": str(e)
                }
                self.logger.error(f"❌ {table_name} 备份失败: {e}")
                
                # 清理可能的临时文件
                if temp_file.exists():
                    temp_file.unlink()
        
        return results
    
    async def truncate_vector_tables(self) -> Dict[str, Any]:
        """清空vector表数据（只清空langchain_pg_embedding）"""
        
        results = {}
        
        # 只清空配置中指定的表（通常只有langchain_pg_embedding）
        truncate_tables = self.config.get("truncate_tables", ["langchain_pg_embedding"])
        
        for table_name in truncate_tables:
            try:
                # 记录清空前的行数（用于统计）
                count_sql = f"SELECT COUNT(*) FROM {table_name}"
                
                start_time = time.time()
                with self.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # 1. 获取清空前的行数
                        cursor.execute(count_sql)
                        rows_before = cursor.fetchone()[0]
                        
                        # 2. 执行TRUNCATE
                        cursor.execute(f"TRUNCATE TABLE {table_name}")
                        
                        # 3. 验证清空结果
                        cursor.execute(count_sql)
                        rows_after = cursor.fetchone()[0]
                
                duration = time.time() - start_time
                
                if rows_after == 0:
                    results[table_name] = {
                        "success": True,
                        "rows_before": rows_before,
                        "rows_after": rows_after,
                        "duration": duration
                    }
                    self.logger.info(f"✅ {table_name} 清空成功: {rows_before}行 -> 0行")
                else:
                    raise Exception(f"清空失败，表中仍有 {rows_after} 行数据")
                    
            except Exception as e:
                results[table_name] = {
                    "success": False,
                    "error": str(e)
                }
                self.logger.error(f"❌ {table_name} 清空失败: {e}")
        
        return results
    
    def get_connection(self):
        """获取pgvector数据库连接（从data_pipeline.config获取配置）"""
        import psycopg2
        
        try:
            # 方法1：如果SCHEMA_TOOLS_CONFIG中有连接字符串，直接使用
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            connection_string = SCHEMA_TOOLS_CONFIG.get("default_db_connection")
            if connection_string:
                conn = psycopg2.connect(connection_string)
            else:
                # 方法2：从app_config获取pgvector数据库配置
                import app_config
                pgvector_config = app_config.PGVECTOR_CONFIG
                conn = psycopg2.connect(
                    host=pgvector_config.get('host'),
                    port=pgvector_config.get('port'),
                    database=pgvector_config.get('dbname'),
                    user=pgvector_config.get('user'),
                    password=pgvector_config.get('password')
                )
            
            # 设置自动提交，避免事务问题
            conn.autocommit = True
            return conn
            
        except Exception as e:
            self.logger.error(f"pgvector数据库连接失败: {e}")
            raise

    def _write_backup_log(self, backup_dir: Path, result: Dict[str, Any]):
        """写入详细的备份日志"""
        log_file = backup_dir / "vector_backup_log.txt"
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("=== Vector Table Backup Log ===\n")
                f.write(f"Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Task ID: {self.task_id or 'Unknown'}\n")
                f.write(f"Duration: {result.get('duration', 0):.2f}s\n\n")
                
                # 备份状态
                f.write("Tables Backup Status:\n")
                for table_name, info in result.get("tables_backed_up", {}).items():
                    if info.get("success", False):
                        f.write(f"✓ {table_name}: {info['row_count']} rows -> {info['backup_file']} ({info['file_size']})\n")
                    else:
                        f.write(f"✗ {table_name}: FAILED - {info.get('error', 'Unknown error')}\n")
                
                # 清空状态
                if result.get("truncate_performed", False):
                    f.write("\nTruncate Status:\n")
                    for table_name, info in result.get("truncate_results", {}).items():
                        if info.get("success", False):
                            f.write(f"✓ {table_name}: TRUNCATED ({info['rows_before']} rows removed)\n")
                        else:
                            f.write(f"✗ {table_name}: FAILED - {info.get('error', 'Unknown error')}\n")
                else:
                    f.write("\nTruncate Status:\n- Not performed\n")
                
                # 错误汇总
                if result.get("errors"):
                    f.write(f"\nErrors: {'; '.join(result['errors'])}\n")
                    
        except Exception as e:
            self.logger.warning(f"写入备份日志失败: {e}")
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}" 