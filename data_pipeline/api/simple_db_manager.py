"""
Data Pipeline API 简化数据库管理器

复用现有的pgvector数据库连接机制，提供Data Pipeline任务的数据库操作功能
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from app_config import PGVECTOR_CONFIG
from core.logging import get_data_pipeline_logger


class SimpleTaskManager:
    """简化的任务管理器，复用现有pgvector连接"""
    
    def __init__(self):
        """初始化任务管理器"""
        self.logger = get_data_pipeline_logger("SimpleTaskManager")
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
                   table_list_file: str,
                   business_context: str,
                   db_name: str = None,
                   **kwargs) -> str:
        """创建新任务"""
        task_id = self.generate_task_id()
        
        # 从 app_config 获取业务数据库连接信息
        from app_config import APP_DB_CONFIG
        
        # 构建业务数据库连接字符串（用于参数记录）
        business_db_connection = self._build_db_connection_string(APP_DB_CONFIG)
        
        # 使用传入的db_name或从APP_DB_CONFIG提取
        if not db_name:
            db_name = APP_DB_CONFIG.get('dbname', 'business_db')
        
        # 构建参数
        parameters = {
            "db_connection": business_db_connection,  # 业务数据库连接（用于schema_workflow执行）
            "table_list_file": table_list_file,
            "business_context": business_context,
            **kwargs
        }
        
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO data_pipeline_tasks (
                        id, task_type, status, parameters, created_by, 
                        db_name, business_context, output_directory
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_id, 
                    'data_workflow', 
                    'pending', 
                    Json(parameters),
                    'api',
                    db_name,
                    business_context,
                    f"./data_pipeline/training_data/{task_id}"
                ))
                
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
                cursor.execute("SELECT * FROM data_pipeline_tasks WHERE id = %s", (task_id,))
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
                    WHERE id = %s
                """, values)
                
                self.logger.info(f"任务状态更新: {task_id} -> {status}")
        except Exception as e:
            self.logger.error(f"任务状态更新失败: {e}")
            raise
    
    def update_step_status(self, task_id: str, step_name: str, step_status: str):
        """更新步骤状态"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE data_pipeline_tasks 
                    SET step_status = jsonb_set(step_status, %s, %s)
                    WHERE id = %s
                """, ([step_name], json.dumps(step_status), task_id))
                
                self.logger.debug(f"步骤状态更新: {task_id}.{step_name} -> {step_status}")
        except Exception as e:
            self.logger.error(f"步骤状态更新失败: {e}")
            raise
    
    def create_execution(self, task_id: str, execution_step: str) -> str:
        """创建执行记录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        execution_id = f"{task_id}_step_{execution_step}_exec_{timestamp}"
        
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO data_pipeline_task_executions (
                        task_id, execution_step, status, execution_id
                    ) VALUES (%s, %s, %s, %s)
                """, (task_id, execution_step, 'running', execution_id))
                
                self.logger.info(f"执行记录创建: {execution_id}")
                return execution_id
        except Exception as e:
            self.logger.error(f"执行记录创建失败: {e}")
            raise
    
    def complete_execution(self, execution_id: str, status: str, error_message: Optional[str] = None):
        """完成执行记录"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # 计算执行时长
                cursor.execute("""
                    SELECT started_at FROM data_pipeline_task_executions 
                    WHERE execution_id = %s
                """, (execution_id,))
                result = cursor.fetchone()
                
                duration_seconds = None
                if result and result[0]:
                    duration_seconds = int((datetime.now() - result[0]).total_seconds())
                
                # 更新执行记录
                update_fields = ["status = %s", "completed_at = CURRENT_TIMESTAMP"]
                values = [status]
                
                if duration_seconds is not None:
                    update_fields.append("duration_seconds = %s")
                    values.append(duration_seconds)
                
                if error_message:
                    update_fields.append("error_message = %s")
                    values.append(error_message)
                
                values.append(execution_id)
                
                cursor.execute(f"""
                    UPDATE data_pipeline_task_executions 
                    SET {', '.join(update_fields)}
                    WHERE execution_id = %s
                """, values)
                
                self.logger.info(f"执行记录完成: {execution_id} -> {status}")
        except Exception as e:
            self.logger.error(f"执行记录完成失败: {e}")
            raise
    
    def record_log(self, task_id: str, log_level: str, message: str, 
                   execution_id: Optional[str] = None, step_name: Optional[str] = None):
        """记录日志到数据库"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO data_pipeline_task_logs (
                        task_id, execution_id, log_level, message, step_name
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (task_id, execution_id, log_level, message, step_name))
        except Exception as e:
            self.logger.error(f"日志记录失败: {e}")
    
    def get_task_logs(self, task_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取任务日志"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM data_pipeline_task_logs 
                    WHERE task_id = %s 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (task_id, limit))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取任务日志失败: {e}")
            raise
    
    def get_task_executions(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务执行记录"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM data_pipeline_task_executions 
                    WHERE task_id = %s 
                    ORDER BY started_at DESC
                """, (task_id,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取执行记录失败: {e}")
            raise
    
    def get_tasks_list(self, limit: int = 50, offset: int = 0, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取任务列表"""
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                where_clause = ""
                params = []
                
                if status_filter:
                    where_clause = "WHERE status = %s"
                    params.append(status_filter)
                
                params.extend([limit, offset])
                
                cursor.execute(f"""
                    SELECT * FROM data_pipeline_tasks 
                    {where_clause}
                    ORDER BY created_at DESC 
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
                cursor.execute("SELECT started_at FROM data_pipeline_tasks WHERE id = %s", (task_id,))
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