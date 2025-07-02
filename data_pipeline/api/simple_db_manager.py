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
                
                # 联表查询获取步骤状态汇总（排除result字段）
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
                             t.output_directory, t.db_name
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