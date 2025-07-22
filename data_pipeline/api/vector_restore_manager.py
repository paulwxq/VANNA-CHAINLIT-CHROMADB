"""
Vector表恢复管理器

提供pgvector表备份文件扫描和数据恢复功能，与VectorTableManager形成完整的备份恢复解决方案
"""

import os
import re
import time
import glob
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import psycopg2
import logging


class VectorRestoreManager:
    """Vector表恢复管理器 - 仿照VectorTableManager设计"""
    
    def __init__(self, base_output_dir: str = None):
        """
        初始化恢复管理器，复用现有配置机制
        
        Args:
            base_output_dir: 基础输出目录，默认从data_pipeline.config获取
        """
        if base_output_dir is None:
            # 从配置文件获取默认目录
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            base_output_dir = SCHEMA_TOOLS_CONFIG.get("output_directory", "./data_pipeline/training_data/")
        
        self.base_output_dir = Path(base_output_dir)
        
        # 从data_pipeline.config获取配置
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        self.config = SCHEMA_TOOLS_CONFIG.get("vector_table_management", {})
        
        # 初始化日志
        self.logger = logging.getLogger("VectorRestoreManager")
        
        # 支持的表名
        self.supported_tables = self.config.get("supported_tables", [
            "langchain_pg_collection",
            "langchain_pg_embedding"
        ])
    
    def scan_backup_files(self, global_only: bool = False, task_id: str = None) -> Dict[str, Any]:
        """
        扫描可用的备份文件
        
        Args:
            global_only: 仅查询全局备份目录（training_data/vector_bak/）
            task_id: 指定task_id，仅查询该任务下的备份文件
            
        Returns:
            包含备份文件信息的字典
        """
        scan_start_time = datetime.now()
        backup_locations = []
        
        try:
            # 确定扫描范围
            if task_id:
                # 仅扫描指定任务
                directories_to_scan = [self.base_output_dir / task_id / "vector_bak"]
            elif global_only:
                # 仅扫描全局目录
                directories_to_scan = [self.base_output_dir / "vector_bak"]
            else:
                # 扫描所有目录
                directories_to_scan = self._get_all_vector_bak_directories()
            
            # 扫描每个目录
            for backup_dir in directories_to_scan:
                if not backup_dir.exists():
                    continue
                    
                # 查找有效的备份集
                backup_sets = self._find_backup_sets(backup_dir)
                if not backup_sets:
                    continue
                
                # 构建备份位置信息
                location_info = self._build_location_info(backup_dir, backup_sets)
                if location_info:
                    backup_locations.append(location_info)
            
            # 构建汇总信息
            summary = self._build_summary(backup_locations, scan_start_time)
            
            return {
                "backup_locations": backup_locations,
                "summary": summary
            }
            
        except Exception as e:
            self.logger.error(f"扫描备份文件失败: {e}")
            raise
    
    def restore_from_backup(self, backup_path: str, timestamp: str, 
                          tables: List[str] = None, pg_conn: str = None,
                          truncate_before_restore: bool = False) -> Dict[str, Any]:
        """
        从备份文件恢复数据
        
        Args:
            backup_path: 备份文件所在的目录路径（相对路径）
            timestamp: 备份文件的时间戳
            tables: 要恢复的表名列表，None表示恢复所有表
            pg_conn: PostgreSQL连接字符串，None则从config获取
            truncate_before_restore: 恢复前是否清空目标表
            
        Returns:
            恢复操作的详细结果
        """
        start_time = time.time()
        
        # 设置默认表列表
        if tables is None:
            tables = self.supported_tables.copy()
        
        # 验证表名
        invalid_tables = [t for t in tables if t not in self.supported_tables]
        if invalid_tables:
            raise ValueError(f"不支持的表名: {invalid_tables}")
        
        # 解析备份路径
        backup_dir = Path(backup_path)
        if not backup_dir.is_absolute():
            # 相对路径，相对于项目根目录
            project_root = Path(__file__).parent.parent.parent
            backup_dir = project_root / backup_path
        
        if not backup_dir.exists():
            raise FileNotFoundError(f"备份目录不存在: {backup_path}")
        
        # 验证备份文件存在
        missing_files = []
        backup_files = {}
        for table_name in tables:
            csv_file = backup_dir / f"{table_name}_{timestamp}.csv"
            if not csv_file.exists():
                missing_files.append(csv_file.name)
            else:
                backup_files[table_name] = csv_file
        
        if missing_files:
            raise FileNotFoundError(f"备份文件不存在: {', '.join(missing_files)}")
        
        # 初始化结果
        result = {
            "restore_performed": True,
            "truncate_performed": truncate_before_restore,
            "backup_info": {
                "backup_path": backup_path,
                "timestamp": timestamp,
                "backup_date": self._parse_timestamp_to_date(timestamp)
            },
            "truncate_results": {},
            "restore_results": {},
            "errors": [],
            "duration": 0
        }
        
        # 临时修改数据库连接配置
        original_config = None
        if pg_conn:
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            original_config = SCHEMA_TOOLS_CONFIG.get("default_db_connection")
            SCHEMA_TOOLS_CONFIG["default_db_connection"] = pg_conn
        
        try:
            # 执行清空操作（如果需要）
            if truncate_before_restore:
                self.logger.info("🗑️ 开始清空目标表...")
                for table_name in tables:
                    truncate_result = self._truncate_table(table_name)
                    result["truncate_results"][table_name] = truncate_result
                    if not truncate_result.get("success", False):
                        result["errors"].append(f"{table_name}表清空失败")
            
            # 执行恢复操作
            self.logger.info("📥 开始恢复表数据...")
            for table_name in tables:
                csv_file = backup_files[table_name]
                restore_result = self._restore_table_from_csv(table_name, csv_file)
                result["restore_results"][table_name] = restore_result
                if not restore_result.get("success", False):
                    result["errors"].append(f"{table_name}表恢复失败")
            
            # 计算总耗时
            result["duration"] = time.time() - start_time
            
            # 记录最终状态
            if result["errors"]:
                self.logger.warning(f"⚠️ Vector表恢复完成，但有错误: {'; '.join(result['errors'])}")
            else:
                self.logger.info(f"✅ Vector表恢复完成，耗时: {result['duration']:.2f}秒")
            
            return result
            
        finally:
            # 恢复原始配置
            if original_config is not None:
                SCHEMA_TOOLS_CONFIG["default_db_connection"] = original_config
    
    def get_connection(self):
        """获取数据库连接 - 完全复用VectorTableManager的连接逻辑"""
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
            
            # 设置自动提交
            conn.autocommit = True
            return conn
            
        except Exception as e:
            self.logger.error(f"pgvector数据库连接失败: {e}")
            raise
    
    def _get_all_vector_bak_directories(self) -> List[Path]:
        """获取所有vector_bak目录"""
        directories = []
        
        # 全局备份目录
        global_backup_dir = self.base_output_dir / "vector_bak"
        if global_backup_dir.exists():
            directories.append(global_backup_dir)
        
        # 任务备份目录 (task_* 和 manual_*)
        for pattern in ["task_*", "manual_*"]:
            for task_dir in self.base_output_dir.glob(pattern):
                if task_dir.is_dir():
                    vector_bak_dir = task_dir / "vector_bak"
                    if vector_bak_dir.exists():
                        directories.append(vector_bak_dir)
        
        return directories
    
    def _find_backup_sets(self, backup_dir: Path) -> List[str]:
        """查找备份目录中的有效备份集"""
        # 查找所有CSV文件
        collection_files = list(backup_dir.glob("langchain_pg_collection_*.csv"))
        embedding_files = list(backup_dir.glob("langchain_pg_embedding_*.csv"))
        
        # 提取时间戳
        collection_timestamps = set()
        embedding_timestamps = set()
        
        for file in collection_files:
            timestamp = self._extract_timestamp_from_filename(file.name)
            if timestamp:
                collection_timestamps.add(timestamp)
        
        for file in embedding_files:
            timestamp = self._extract_timestamp_from_filename(file.name)
            if timestamp:
                embedding_timestamps.add(timestamp)
        
        # 找到同时存在两个文件的时间戳
        valid_timestamps = collection_timestamps & embedding_timestamps
        
        # 按时间戳降序排列（最新的在前）
        return sorted(valid_timestamps, reverse=True)
    
    def _extract_timestamp_from_filename(self, filename: str) -> Optional[str]:
        """从文件名中提取时间戳"""
        # 匹配格式：langchain_pg_collection_20250722_010318.csv
        pattern = r'langchain_pg_(?:collection|embedding)_(\d{8}_\d{6})\.csv'
        match = re.search(pattern, filename)
        return match.group(1) if match else None
    
    def _build_location_info(self, backup_dir: Path, backup_sets: List[str]) -> Optional[Dict[str, Any]]:
        """构建备份位置信息"""
        if not backup_sets:
            return None
        
        # 确定位置类型和相关信息
        relative_path = self._get_relative_path(backup_dir)
        location_type, task_id = self._determine_location_type(backup_dir)
        
        # 构建备份信息列表
        backups = []
        for timestamp in backup_sets:
            backup_info = self._build_backup_info(backup_dir, timestamp)
            if backup_info:
                backups.append(backup_info)
        
        location_info = {
            "type": location_type,
            "relative_path": relative_path,
            "backups": backups
        }
        
        if task_id:
            location_info["task_id"] = task_id
        
        return location_info
    
    def _get_relative_path(self, backup_dir: Path) -> str:
        """获取相对路径（Unix风格）"""
        try:
            # 计算相对于项目根目录的路径
            project_root = Path(__file__).parent.parent.parent
            relative_path = backup_dir.relative_to(project_root)
            # 转换为Unix风格路径
            return "./" + str(relative_path).replace("\\", "/")
        except ValueError:
            # 如果无法计算相对路径，直接转换
            return str(backup_dir).replace("\\", "/")
    
    def _determine_location_type(self, backup_dir: Path) -> tuple:
        """确定位置类型和task_id"""
        backup_dir_str = str(backup_dir)
        
        if "/vector_bak" in backup_dir_str.replace("\\", "/"):
            parent = backup_dir.parent.name
            if parent.startswith(("task_", "manual_")):
                return "task", parent
            else:
                return "global", None
        
        return "unknown", None
    
    def _build_backup_info(self, backup_dir: Path, timestamp: str) -> Optional[Dict[str, Any]]:
        """构建单个备份信息"""
        try:
            collection_file = backup_dir / f"langchain_pg_collection_{timestamp}.csv"
            embedding_file = backup_dir / f"langchain_pg_embedding_{timestamp}.csv"
            log_file = backup_dir / "vector_backup_log.txt"
            
            # 检查文件存在性
            if not (collection_file.exists() and embedding_file.exists()):
                return None
            
            # 获取文件大小
            collection_size = self._format_file_size(collection_file.stat().st_size)
            embedding_size = self._format_file_size(embedding_file.stat().st_size)
            
            # 解析备份日期
            backup_date = self._parse_timestamp_to_date(timestamp)
            
            return {
                "timestamp": timestamp,
                "collection_file": collection_file.name,
                "embedding_file": embedding_file.name,
                "collection_size": collection_size,
                "embedding_size": embedding_size,
                "backup_date": backup_date,
                "has_log": log_file.exists(),
                "log_file": log_file.name if log_file.exists() else None
            }
            
        except Exception as e:
            self.logger.warning(f"构建备份信息失败: {e}")
            return None
    
    def _parse_timestamp_to_date(self, timestamp: str) -> str:
        """将时间戳转换为可读日期格式"""
        try:
            # 解析格式：20250722_010318
            dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return timestamp
    
    def _build_summary(self, backup_locations: List[Dict], scan_start_time: datetime) -> Dict[str, Any]:
        """构建汇总信息"""
        total_backup_sets = sum(len(loc["backups"]) for loc in backup_locations)
        global_backups = sum(len(loc["backups"]) for loc in backup_locations if loc["type"] == "global")
        task_backups = total_backup_sets - global_backups
        
        return {
            "total_locations": len(backup_locations),
            "total_backup_sets": total_backup_sets,
            "global_backups": global_backups,
            "task_backups": task_backups,
            "scan_time": scan_start_time.isoformat()
        }
    
    def _restore_table_from_csv(self, table_name: str, csv_file: Path) -> Dict[str, Any]:
        """从CSV文件恢复单个表 - 使用COPY FROM STDIN"""
        try:
            start_time = time.time()
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 检查是否是embedding表，需要特殊处理JSON格式
                    if table_name == "langchain_pg_embedding":
                        self._restore_embedding_table_with_json_fix(cursor, csv_file)
                    else:
                        # 其他表直接使用COPY FROM STDIN
                        with open(csv_file, 'r', encoding='utf-8') as f:
                            # 使用CSV HEADER选项自动跳过表头，无需手动next(f)
                            cursor.copy_expert(
                                f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, HEADER)",
                                f
                            )
                    
                    # 验证导入结果
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    rows_restored = cursor.fetchone()[0]
            
            duration = time.time() - start_time
            file_size = csv_file.stat().st_size
            
            return {
                "success": True,
                "source_file": csv_file.name,
                "rows_restored": rows_restored,
                "file_size": self._format_file_size(file_size),
                "duration": duration
            }
            
        except Exception as e:
            return {
                "success": False,
                "source_file": csv_file.name,
                "error": str(e)
            }
    
    def _truncate_table(self, table_name: str) -> Dict[str, Any]:
        """清空指定表"""
        try:
            start_time = time.time()
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 获取清空前的行数
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    rows_before = cursor.fetchone()[0]
                    
                    # 执行TRUNCATE
                    cursor.execute(f"TRUNCATE TABLE {table_name}")
                    
                    # 验证清空结果
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    rows_after = cursor.fetchone()[0]
            
            duration = time.time() - start_time
            
            if rows_after == 0:
                return {
                    "success": True,
                    "rows_before": rows_before,
                    "rows_after": rows_after,
                    "duration": duration
                }
            else:
                raise Exception(f"清空失败，表中仍有 {rows_after} 行数据")
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
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
    
    def _restore_embedding_table_with_json_fix(self, cursor, csv_file: Path):
        """恢复embedding表，修复cmetadata列的JSON格式问题"""
        import csv
        import json
        import ast
        import io
        
        # 读取CSV并修复JSON格式
        corrected_data = io.StringIO()
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            writer = csv.writer(corrected_data)
            
            # 处理表头
            header = next(reader)
            writer.writerow(header)
            
            # 找到cmetadata列的索引
            try:
                cmetadata_index = header.index('cmetadata')
            except ValueError:
                # 如果没有cmetadata列，直接使用原始CSV
                corrected_data.seek(0)
                corrected_data.truncate(0)
                f.seek(0)
                corrected_data.write(f.read())
                corrected_data.seek(0)
                cursor.copy_expert(
                    "COPY langchain_pg_embedding FROM STDIN WITH (FORMAT CSV, HEADER)",
                    corrected_data
                )
                return
            
            # 处理数据行
            for row in reader:
                if len(row) > cmetadata_index and row[cmetadata_index]:
                    try:
                        # 尝试将Python字典格式转换为JSON格式
                        # 如果已经是JSON格式，json.loads会成功
                        if row[cmetadata_index].startswith('{') and row[cmetadata_index].endswith('}'):
                            try:
                                # 先尝试作为JSON解析
                                json.loads(row[cmetadata_index])
                                # 已经是有效JSON，不需要转换
                            except json.JSONDecodeError:
                                # 不是有效JSON，尝试作为Python字典解析并转换
                                try:
                                    python_dict = ast.literal_eval(row[cmetadata_index])
                                    row[cmetadata_index] = json.dumps(python_dict, ensure_ascii=False)
                                except (ValueError, SyntaxError):
                                    # 如果都失败了，记录错误但继续处理
                                    self.logger.warning(f"无法解析cmetadata: {row[cmetadata_index]}")
                    except Exception as e:
                        self.logger.warning(f"处理cmetadata时出错: {e}")
                
                writer.writerow(row)
        
        # 使用修复后的数据进行导入
        corrected_data.seek(0)
        cursor.copy_expert(
            "COPY langchain_pg_embedding FROM STDIN WITH (FORMAT CSV, HEADER)",
            corrected_data
        )