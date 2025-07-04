"""
Data Pipeline API 简化数据库管理器

复用现有的pgvector数据库连接机制，提供Data Pipeline任务的数据库操作功能
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from app_config import PGVECTOR_CONFIG
import logging


class SimpleTaskManager:
    """简化的任务管理器，复用现有pgvector连接"""
    
    def __init__(self):
        """初始化任务管理器"""
        # 使用简单的控制台日志，不使用文件日志
        self.logger = logging.getLogger("SimpleTaskManager")
        self.logger.setLevel(logging.INFO)
        self._connection = None
    
    def _get_connection(self):
        """获取pgvector数据库连接"""
        if self._connection is None or self._connection.closed:
            try:
                self._connection = psycopg2.connect(
                    host=PGVECTOR_CONFIG.get('host'),
                    port=PGVECTOR_CONFIG.get('port'),
                    database=PGVECTOR_CONFIG.get('dbname'),
                    user=PGVECTOR_CONFIG.get('user'),
                    password=PGVECTOR_CONFIG.get('password')
                )
                self._connection.autocommit = True
            except Exception as e:
                self.logger.error(f"pgvector数据库连接失败: {e}")
                raise
        return self._connection
    
    def close_connection(self):
        """关闭数据库连接"""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None
    
    def generate_task_id(self) -> str:
        """生成任务ID，格式: task_YYYYMMDD_HHMMSS"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"task_{timestamp}"
    
    def create_task(self, 
                   table_list_file: str = None,
                   business_context: str = None,
                   db_name: str = None,
                   db_connection: str = None,
                   task_name: str = None,
                   **kwargs) -> str:
        """创建新任务"""
        task_id = self.generate_task_id()
        
        # 处理数据库连接和名称
        if db_connection:
            # 使用传入的 db_connection 参数
            business_db_connection = db_connection
            # 如果没有提供 db_name，从连接字符串中提取
            if not db_name:
                db_name = self._extract_db_name(db_connection)
        else:
            # 从 app_config 获取业务数据库连接信息
            from app_config import APP_DB_CONFIG
            business_db_connection = self._build_db_connection_string(APP_DB_CONFIG)
            # 使用传入的db_name或从APP_DB_CONFIG提取
            if not db_name:
                db_name = APP_DB_CONFIG.get('dbname', 'business_db')
        
        # 处理table_list_file参数
        # 如果未提供，将在执行时检查任务目录中的table_list.txt文件
        task_table_list_file = table_list_file
        if not task_table_list_file:
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            upload_config = SCHEMA_TOOLS_CONFIG.get("file_upload", {})
            target_filename = upload_config.get("target_filename", "table_list.txt")
            # 使用相对于任务目录的路径
            task_table_list_file = f"{{task_directory}}/{target_filename}"
        
        # 构建参数
        parameters = {
            "db_connection": business_db_connection,  # 业务数据库连接（用于schema_workflow执行）
            "table_list_file": task_table_list_file,
            "business_context": business_context or "数据库管理系统",
            "file_upload_mode": table_list_file is None,  # 标记是否使用文件上传模式
            **kwargs
        }
        
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # 创建任务记录
                cursor.execute("""
                    INSERT INTO data_pipeline_tasks (
                        task_id, task_name, task_type, status, parameters, created_type, 
                        by_user, db_name, output_directory
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_id, 
                    task_name,
                    'data_workflow', 
                    'pending', 
                    Json(parameters),
                    'api',
                    'guest',
                    db_name,
                    f"data_pipeline/training_data/{task_id}"
                ))
                
                # 预创建所有步骤记录（策略A）
                step_names = ['ddl_generation', 'qa_generation', 'sql_validation', 'training_load']
                for step_name in step_names:
                    cursor.execute("""
                        INSERT INTO data_pipeline_task_steps (
                            task_id, step_name, step_status
                        ) VALUES (%s, %s, %s)
                    """, (task_id, step_name, 'pending'))
            
            # 创建任务目录
            try:
                from data_pipeline.api.simple_file_manager import SimpleFileManager
                file_manager = SimpleFileManager()
                success = file_manager.create_task_directory(task_id)
                if success:
                    self.logger.info(f"任务目录创建成功: {task_id}")
                else:
                    self.logger.warning(f"任务目录创建失败，但任务记录已保存: {task_id}")
            except Exception as dir_error:
                self.logger.warning(f"创建任务目录时出错: {dir_error}，但任务记录已保存: {task_id}")
                
            self.logger.info(f"任务创建成功: {task_id}")
            return task_id
            
        except Exception as e:
            self.logger.error(f"任务创建失败: {e}")
            raise
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM data_pipeline_tasks WHERE task_id = %s", (task_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"获取任务信息失败: {e}")
            raise
    
    def update_task_status(self, task_id: str, status: str, error_message: Optional[str] = None):
        """更新任务状态"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                update_fields = ["status = %s"]
                values = [status]
                
                if status == 'in_progress' and not self._get_task_started_at(task_id):
                    update_fields.append("started_at = CURRENT_TIMESTAMP")
                
                if status in ['completed', 'failed']:
                    update_fields.append("completed_at = CURRENT_TIMESTAMP")
                
                if error_message:
                    update_fields.append("error_message = %s")
                    values.append(error_message)
                
                values.append(task_id)
                
                cursor.execute(f"""
                    UPDATE data_pipeline_tasks 
                    SET {', '.join(update_fields)}
                    WHERE task_id = %s
                """, values)
                
                self.logger.info(f"任务状态更新: {task_id} -> {status}")
        except Exception as e:
            self.logger.error(f"任务状态更新失败: {e}")
            raise
    
    def update_step_status(self, task_id: str, step_name: str, step_status: str, error_message: Optional[str] = None):
        """更新步骤状态"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                update_fields = ["step_status = %s"]
                values = [step_status]
                
                # 如果状态是running，记录开始时间
                if step_status == 'running':
                    update_fields.append("started_at = CURRENT_TIMESTAMP")
                
                # 如果状态是completed或failed，记录完成时间
                if step_status in ['completed', 'failed']:
                    update_fields.append("completed_at = CURRENT_TIMESTAMP")
                
                # 如果有错误信息，记录错误信息
                if error_message:
                    update_fields.append("error_message = %s")
                    values.append(error_message)
                
                values.extend([task_id, step_name])
                
                cursor.execute(f"""
                    UPDATE data_pipeline_task_steps 
                    SET {', '.join(update_fields)}
                    WHERE task_id = %s AND step_name = %s
                """, values)
                
                self.logger.debug(f"步骤状态更新: {task_id}.{step_name} -> {step_status}")
        except Exception as e:
            self.logger.error(f"步骤状态更新失败: {e}")
            raise
    
    def update_step_execution_id(self, task_id: str, step_name: str, execution_id: str):
        """更新步骤的execution_id"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE data_pipeline_task_steps 
                    SET execution_id = %s
                    WHERE task_id = %s AND step_name = %s
                """, (execution_id, task_id, step_name))
                
                self.logger.debug(f"步骤execution_id更新: {task_id}.{step_name} -> {execution_id}")
        except Exception as e:
            self.logger.error(f"步骤execution_id更新失败: {e}")
            raise
    
    def start_step(self, task_id: str, step_name: str) -> str:
        """开始执行步骤"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        execution_id = f"{task_id}_step_{step_name}_exec_{timestamp}"
        
        try:
            # 更新步骤状态为running并设置execution_id
            self.update_step_status(task_id, step_name, 'running')
            self.update_step_execution_id(task_id, step_name, execution_id)
                
            self.logger.info(f"步骤开始执行: {task_id}.{step_name} -> {execution_id}")
            return execution_id
        except Exception as e:
            self.logger.error(f"步骤开始执行失败: {e}")
            raise
    
    def complete_step(self, task_id: str, step_name: str, status: str, error_message: Optional[str] = None):
        """完成步骤执行"""
        try:
            self.update_step_status(task_id, step_name, status, error_message)
            self.logger.info(f"步骤执行完成: {task_id}.{step_name} -> {status}")
        except Exception as e:
            self.logger.error(f"步骤执行完成失败: {e}")
            raise
    
    def get_task_steps(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有步骤状态"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM data_pipeline_task_steps 
                    WHERE task_id = %s 
                    ORDER BY 
                        CASE step_name 
                          WHEN 'ddl_generation' THEN 1
                          WHEN 'qa_generation' THEN 2
                          WHEN 'sql_validation' THEN 3
                          WHEN 'training_load' THEN 4
                          ELSE 5 
                        END
                """, (task_id,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取任务步骤状态失败: {e}")
            raise
    
    def get_step_status(self, task_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """获取特定步骤的状态"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM data_pipeline_task_steps 
                    WHERE task_id = %s AND step_name = %s
                """, (task_id, step_name))
                
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"获取步骤状态失败: {e}")
            raise
    
    def get_tasks_list(self, limit: int = 50, offset: int = 0, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取任务列表"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                where_clause = ""
                params = []
                
                if status_filter:
                    where_clause = "WHERE t.status = %s"
                    params.append(status_filter)
                
                params.extend([limit, offset])
                
                # 联表查询获取步骤状态汇总（包含新增字段）
                cursor.execute(f"""
                    SELECT 
                        t.task_id,
                        t.task_name,
                        t.task_type,
                        t.status,
                        t.parameters,
                        t.error_message,
                        t.created_at,
                        t.started_at,
                        t.completed_at,
                        t.created_type,
                        t.by_user,
                        t.output_directory,
                        t.db_name,
                        COALESCE(t.directory_exists, TRUE) as directory_exists,
                        t.updated_at,
                        CASE 
                            WHEN COUNT(s.step_name) = 0 THEN NULL
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'failed') > 0 THEN 'failed'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'running') > 0 THEN 'running'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'completed') = COUNT(s.step_name) THEN 'all_completed'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'completed') > 0 THEN 'partial_completed'
                            ELSE 'pending'
                        END as step_status
                    FROM data_pipeline_tasks t
                    LEFT JOIN data_pipeline_task_steps s ON t.task_id = s.task_id
                    {where_clause}
                    GROUP BY t.task_id, t.task_name, t.task_type, t.status, t.parameters, t.error_message, 
                             t.created_at, t.started_at, t.completed_at, t.created_type, t.by_user, 
                             t.output_directory, t.db_name, t.directory_exists, t.updated_at
                    ORDER BY t.created_at DESC 
                    LIMIT %s OFFSET %s
                """, params)
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取任务列表失败: {e}")
            raise
    
    def _get_task_started_at(self, task_id: str) -> Optional[datetime]:
        """获取任务开始时间"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT started_at FROM data_pipeline_tasks WHERE task_id = %s", (task_id,))
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except Exception:
            return None
    
    def _build_db_connection_string(self, db_config: dict) -> str:
        """构建数据库连接字符串"""
        try:
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 5432)
            dbname = db_config.get('dbname', 'database')
            user = db_config.get('user', 'postgres')
            password = db_config.get('password', '')
            
            return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        except Exception:
            return "postgresql://localhost:5432/database"
    
    def _extract_db_name(self, connection_string: str) -> str:
        """从连接字符串提取数据库名称"""
        try:
            if '/' in connection_string:
                db_name = connection_string.split('/')[-1]
                if '?' in db_name:
                    db_name = db_name.split('?')[0]
                return db_name if db_name else "database"
            else:
                return "database"
        except Exception:
            return "database"

    def query_tasks_advanced(self, 
                            page: int = 1,
                            page_size: int = 20,
                            status: str = None,
                            task_name: str = None,
                            created_by: str = None,
                            db_name: str = None,
                            created_time_start: str = None,
                            created_time_end: str = None,
                            started_time_start: str = None,
                            started_time_end: str = None,
                            completed_time_start: str = None,
                            completed_time_end: str = None,
                            sort_by: str = "created_at",
                            sort_order: str = "desc") -> dict:
        """
        高级任务查询，支持复杂筛选、排序、分页
        
        Args:
            page: 页码，必须大于0，默认1
            page_size: 每页大小，1-100之间，默认20
            status: 可选，任务状态筛选
            task_name: 可选，任务名称模糊搜索
            created_by: 可选，创建者精确匹配
            db_name: 可选，数据库名称精确匹配
            created_time_start: 可选，创建时间范围开始
            created_time_end: 可选，创建时间范围结束
            started_time_start: 可选，开始时间范围开始
            started_time_end: 可选，开始时间范围结束
            completed_time_start: 可选，完成时间范围开始
            completed_time_end: 可选，完成时间范围结束
            sort_by: 可选，排序字段，默认"created_at"
            sort_order: 可选，排序方向，默认"desc"
        
        Returns:
            {
                "tasks": [...],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total": 150,
                    "total_pages": 8,
                    "has_next": True,
                    "has_prev": False
                }
            }
        """
        try:
            import time
            start_time = time.time()
            
            # 参数验证和处理
            page = max(page, 1)
            page_size = min(max(page_size, 1), 100)  # 限制在1-100之间
            offset = (page - 1) * page_size
            
            # 构建WHERE条件
            where_conditions = []
            params = []
            
            # 状态筛选
            if status:
                where_conditions.append("t.status = %s")
                params.append(status)
            
            # 任务名称模糊搜索
            if task_name:
                where_conditions.append("t.task_name ILIKE %s")
                params.append(f"%{task_name}%")
            
            # 创建者精确匹配
            if created_by:
                where_conditions.append("t.by_user = %s")
                params.append(created_by)
            
            # 数据库名称精确匹配
            if db_name:
                where_conditions.append("t.db_name = %s")
                params.append(db_name)
            
            # 时间范围筛选
            # 创建时间范围
            if created_time_start:
                where_conditions.append("t.created_at >= %s")
                params.append(created_time_start)
            if created_time_end:
                where_conditions.append("t.created_at <= %s")
                params.append(created_time_end)
            
            # 开始时间范围
            if started_time_start:
                where_conditions.append("t.started_at >= %s")
                params.append(started_time_start)
            if started_time_end:
                where_conditions.append("t.started_at <= %s")
                params.append(started_time_end)
            
            # 完成时间范围
            if completed_time_start:
                where_conditions.append("t.completed_at >= %s")
                params.append(completed_time_start)
            if completed_time_end:
                where_conditions.append("t.completed_at <= %s")
                params.append(completed_time_end)
            
            # 构建WHERE子句
            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)
            
            # 构建ORDER BY子句
            # 验证排序字段白名单
            allowed_sort_fields = ['created_at', 'started_at', 'completed_at', 'task_name', 'status']
            if sort_by not in allowed_sort_fields:
                sort_by = 'created_at'
            
            # 验证排序方向
            sort_order_upper = sort_order.upper()
            if sort_order_upper not in ['ASC', 'DESC']:
                sort_order_upper = 'DESC'
            
            order_clause = f"ORDER BY t.{sort_by} {sort_order_upper}"
            
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # 首先获取总数
                count_query = f"""
                    SELECT COUNT(*) as total
                    FROM data_pipeline_tasks t
                    {where_clause}
                """
                cursor.execute(count_query, params)
                total_count = cursor.fetchone()['total']
                
                # 然后获取分页数据
                data_params = params + [page_size, offset]
                data_query = f"""
                    SELECT 
                        t.task_id,
                        t.task_name,
                        t.task_type,
                        t.status,
                        t.parameters,
                        t.error_message,
                        t.created_at,
                        t.started_at,
                        t.completed_at,
                        t.created_type,
                        t.by_user,
                        t.output_directory,
                        t.db_name,
                        COALESCE(t.directory_exists, TRUE) as directory_exists,
                        t.updated_at,
                        CASE 
                            WHEN COUNT(s.step_name) = 0 THEN NULL
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'failed') > 0 THEN 'failed'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'running') > 0 THEN 'running'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'completed') = COUNT(s.step_name) THEN 'all_completed'
                            WHEN COUNT(s.step_name) FILTER (WHERE s.step_status = 'completed') > 0 THEN 'partial_completed'
                            ELSE 'pending'
                        END as step_status
                    FROM data_pipeline_tasks t
                    LEFT JOIN data_pipeline_task_steps s ON t.task_id = s.task_id
                    {where_clause}
                    GROUP BY t.task_id, t.task_name, t.task_type, t.status, t.parameters, t.error_message, 
                             t.created_at, t.started_at, t.completed_at, t.created_type, t.by_user, 
                             t.output_directory, t.db_name, t.directory_exists, t.updated_at
                    {order_clause}
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(data_query, data_params)
                tasks = [dict(row) for row in cursor.fetchall()]
                
                # 计算分页信息
                total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
                has_next = page < total_pages
                has_prev = page > 1
                
                query_time = time.time() - start_time
                
                return {
                    "tasks": tasks,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total_count,
                        "total_pages": total_pages,
                        "has_next": has_next,
                        "has_prev": has_prev
                    },
                    "query_time": f"{query_time:.3f}s"
                }
                
        except Exception as e:
            self.logger.error(f"高级任务查询失败: {e}")
            raise

    def query_logs_advanced(self,
                           task_id: str,
                           page: int = 1,
                           page_size: int = 50,
                           level: str = None,
                           start_time: str = None,
                           end_time: str = None,
                           keyword: str = None,
                           logger_name: str = None,
                           step_name: str = None,
                           sort_by: str = "timestamp",
                           sort_order: str = "desc") -> dict:
        """
        高级日志查询，支持复杂筛选、排序、分页
        
        Args:
            task_id: 任务ID
            page: 页码，必须大于0，默认1
            page_size: 每页大小，1-500之间，默认50
            level: 可选，日志级别筛选 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            start_time: 可选，开始时间范围 (YYYY-MM-DD HH:MM:SS)
            end_time: 可选，结束时间范围 (YYYY-MM-DD HH:MM:SS)
            keyword: 可选，关键字搜索（消息内容模糊匹配）
            logger_name: 可选，日志记录器名称精确匹配
            step_name: 可选，执行步骤名称精确匹配
            sort_by: 可选，排序字段，默认"timestamp"
            sort_order: 可选，排序方向，默认"desc"
        
        Returns:
            {
                "logs": [...],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 1000,
                    "total_pages": 20,
                    "has_next": True,
                    "has_prev": False
                },
                "log_file_info": {...}
            }
        """
        try:
            import time
            
            start_query_time = time.time()
            
            # 参数验证和处理
            page = max(page, 1)
            page_size = min(max(page_size, 1), 500)  # 限制在1-500之间
            
            # 获取日志文件路径
            project_root = Path(__file__).parent.parent.parent
            task_dir = project_root / "data_pipeline" / "training_data" / task_id
            log_file = task_dir / "data_pipeline.log"
            
            # 检查日志文件是否存在
            if not log_file.exists():
                return {
                    "logs": [],
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    },
                    "log_file_info": {
                        "exists": False,
                        "file_path": str(log_file),
                        "error": "日志文件不存在"
                    },
                    "query_time": f"{time.time() - start_query_time:.3f}s"
                }
            
            # 读取并解析日志文件
            parsed_logs = self._parse_log_file(log_file)
            
            # 应用过滤器
            filtered_logs = self._filter_logs(
                parsed_logs,
                level=level,
                start_time=start_time,
                end_time=end_time,
                keyword=keyword,
                logger_name=logger_name,
                step_name=step_name
            )
            
            # 排序
            sorted_logs = self._sort_logs(filtered_logs, sort_by, sort_order)
            
            # 分页
            total_count = len(sorted_logs)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_logs = sorted_logs[start_index:end_index]
            
            # 计算分页信息
            total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
            has_next = page < total_pages
            has_prev = page > 1
            
            # 获取文件信息
            file_stat = log_file.stat()
            log_file_info = {
                "exists": True,
                "file_path": str(log_file),
                "file_size": file_stat.st_size,
                "file_size_formatted": self._format_file_size(file_stat.st_size),
                "last_modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "total_lines": len(parsed_logs)
            }
            
            query_time = time.time() - start_query_time
            
            return {
                "logs": paginated_logs,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev
                },
                "log_file_info": log_file_info,
                "query_time": f"{query_time:.3f}s"
            }
            
        except Exception as e:
            self.logger.error(f"日志查询失败: {e}")
            return {
                "logs": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False
                },
                "log_file_info": {
                    "exists": False,
                    "error": str(e)
                },
                "query_time": "0.000s"
            }
    
    def _parse_log_file(self, log_file_path: Path) -> List[Dict[str, Any]]:
        """
        解析日志文件，提取结构化信息
        """
        try:
            logs = []
            with open(log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 日志行格式: 2025-07-01 14:30:52 [INFO] SimpleWorkflowExecutor: 任务开始执行
            log_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.+?): (.+)$'
            current_log = None
            line_number = 0
            
            for line in lines:
                line_number += 1
                line = line.rstrip('\n\r')
                
                if not line.strip():
                    continue
                
                match = re.match(log_pattern, line)
                if match:
                    # 如果有之前的日志，先保存
                    if current_log:
                        logs.append(current_log)
                    
                    # 解析新的日志条目
                    timestamp, level, logger_name, message = match.groups()
                    
                    # 尝试从日志记录器名称中提取步骤信息
                    step_name = self._extract_step_from_logger(logger_name)
                    
                    current_log = {
                        "timestamp": timestamp,
                        "level": level,
                        "logger": logger_name,
                        "step": step_name,
                        "message": message,
                        "line_number": line_number
                    }
                else:
                    # 多行日志（如异常堆栈），追加到当前日志的消息中
                    if current_log:
                        current_log["message"] += f"\n{line}"
            
            # 保存最后一个日志条目
            if current_log:
                logs.append(current_log)
            
            return logs
            
        except Exception as e:
            self.logger.error(f"解析日志文件失败: {e}")
            return []
    
    def _extract_step_from_logger(self, logger_name: str) -> Optional[str]:
        """
        从日志记录器名称中提取步骤信息
        """
        # 映射日志记录器名称到步骤名称
        logger_to_step = {
            "DDLGenerator": "ddl_generation",
            "QAGenerator": "qa_generation", 
            "QSGenerator": "qa_generation",
            "SQLValidator": "sql_validation",
            "TrainingDataLoader": "training_load",
            "VannaTrainer": "training_load",
            "SchemaWorkflowOrchestrator": None,  # 总体协调器
            "SimpleWorkflowExecutor": None,      # 工作流执行器
        }
        
        return logger_to_step.get(logger_name)
    
    def _filter_logs(self, logs: List[Dict[str, Any]], **filters) -> List[Dict[str, Any]]:
        """
        根据条件过滤日志
        """
        filtered = logs
        
        # 日志级别过滤
        if filters.get('level'):
            level = filters['level'].upper()
            filtered = [log for log in filtered if log.get('level') == level]
        
        # 时间范围过滤
        if filters.get('start_time'):
            start_time = filters['start_time']
            filtered = [log for log in filtered if log.get('timestamp', '') >= start_time]
        
        if filters.get('end_time'):
            end_time = filters['end_time']
            filtered = [log for log in filtered if log.get('timestamp', '') <= end_time]
        
        # 关键字搜索（消息内容模糊匹配）
        if filters.get('keyword'):
            keyword = filters['keyword'].lower()
            filtered = [log for log in filtered 
                       if keyword in log.get('message', '').lower()]
        
        # 日志记录器名称精确匹配
        if filters.get('logger_name'):
            logger_name = filters['logger_name']
            filtered = [log for log in filtered if log.get('logger') == logger_name]
        
        # 步骤名称精确匹配
        if filters.get('step_name'):
            step_name = filters['step_name']
            filtered = [log for log in filtered if log.get('step') == step_name]
        
        return filtered
    
    def _sort_logs(self, logs: List[Dict[str, Any]], sort_by: str, sort_order: str) -> List[Dict[str, Any]]:
        """
        对日志进行排序
        """
        # 验证排序字段
        allowed_sort_fields = ['timestamp', 'level', 'logger', 'step', 'line_number']
        if sort_by not in allowed_sort_fields:
            sort_by = 'timestamp'
        
        # 验证排序方向
        reverse = sort_order.lower() == 'desc'
        
        try:
            # 特殊处理时间戳排序
            if sort_by == 'timestamp':
                return sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=reverse)
            else:
                return sorted(logs, key=lambda x: x.get(sort_by, ''), reverse=reverse)
        except Exception as e:
            self.logger.error(f"日志排序失败: {e}")
            return logs
    
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