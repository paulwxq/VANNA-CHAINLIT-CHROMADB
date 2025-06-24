"""
QA反馈数据管理器 - 复用Vanna连接版本
用于处理用户对问答结果的点赞/点踩反馈，并将反馈转化为训练数据
"""
import app_config
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.exc import OperationalError, ProgrammingError
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import logging

class QAFeedbackManager:
    """QA反馈数据管理器 - 复用Vanna连接版本"""
    
    def __init__(self, vanna_instance=None):
        """初始化数据库连接
        
        Args:
            vanna_instance: 可选的vanna实例，用于复用其数据库连接
        """
        self.engine = None
        self.vanna_instance = vanna_instance
        self._init_database_connection()
        self._ensure_table_exists()
    
    def _init_database_connection(self):
        """初始化数据库连接"""
        try:
            # 方案1: 优先尝试复用vanna连接
            if self.vanna_instance and hasattr(self.vanna_instance, 'engine'):
                self.engine = self.vanna_instance.engine
                print(f"[QAFeedbackManager] 复用Vanna数据库连接")
                return
            
            # 方案2: 创建新的连接（原有方式）
            db_config = app_config.APP_DB_CONFIG
            connection_string = (
                f"postgresql://{db_config['user']}:{db_config['password']}"
                f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
            )
            # 使用连接池配置
            self.engine = create_engine(
                connection_string, 
                echo=False,
                pool_size=5,          # 连接池大小
                max_overflow=10,      # 最大溢出连接数
                pool_timeout=30,      # 获取连接超时
                pool_recycle=3600     # 连接回收时间(1小时)
            )
            
            # 测试连接
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print(f"[QAFeedbackManager] 数据库连接成功: {db_config['host']}:{db_config['port']}/{db_config['dbname']}")
            
        except Exception as e:
            print(f"[ERROR] QAFeedbackManager数据库连接失败: {e}")
            raise
    
    def _ensure_table_exists(self):
        """检查并创建qa_feedback表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS qa_feedback (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            sql TEXT NOT NULL,
            is_thumb_up BOOLEAN NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_in_training_data BOOLEAN DEFAULT FALSE,
            update_time TIMESTAMP
        );
        """
        
        # 创建索引SQL
        create_indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_qa_feedback_user_id ON qa_feedback(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_qa_feedback_create_time ON qa_feedback(create_time);",
            "CREATE INDEX IF NOT EXISTS idx_qa_feedback_is_thumb_up ON qa_feedback(is_thumb_up);",
            "CREATE INDEX IF NOT EXISTS idx_qa_feedback_is_in_training ON qa_feedback(is_in_training_data);"
        ]
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    # 创建表
                    conn.execute(text(create_table_sql))
                    
                    # 创建索引
                    for index_sql in create_indexes_sql:
                        conn.execute(text(index_sql))
                    
            print("[QAFeedbackManager] qa_feedback表检查/创建成功")
            
        except Exception as e:
            print(f"[ERROR] qa_feedback表创建失败: {e}")
            raise
    
    def add_feedback(self, question: str, sql: str, is_thumb_up: bool, user_id: str = "guest") -> int:
        """添加反馈记录
        
        Args:
            question: 用户问题
            sql: 生成的SQL
            is_thumb_up: 是否点赞
            user_id: 用户ID
            
        Returns:
            新创建记录的ID
        """
        insert_sql = """
        INSERT INTO qa_feedback (question, sql, is_thumb_up, user_id, create_time)
        VALUES (:question, :sql, :is_thumb_up, :user_id, :create_time)
        RETURNING id
        """
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    result = conn.execute(text(insert_sql), {
                        'question': question,
                        'sql': sql,
                        'is_thumb_up': is_thumb_up,
                        'user_id': user_id,
                        'create_time': datetime.now()
                    })
                    feedback_id = result.fetchone()[0]
                
            print(f"[QAFeedbackManager] 反馈记录创建成功, ID: {feedback_id}")
            return feedback_id
            
        except Exception as e:
            print(f"[ERROR] 添加反馈记录失败: {e}")
            raise
    
    def query_feedback(self, page: int = 1, page_size: int = 20, 
                      is_thumb_up: Optional[bool] = None,
                      create_time_start: Optional[str] = None,
                      create_time_end: Optional[str] = None,
                      is_in_training_data: Optional[bool] = None,
                      sort_by: str = "create_time",
                      sort_order: str = "desc") -> Tuple[List[Dict], int]:
        """查询反馈记录
        
        Args:
            page: 页码 (从1开始)
            page_size: 每页大小
            is_thumb_up: 是否点赞筛选
            create_time_start: 创建时间开始
            create_time_end: 创建时间结束
            is_in_training_data: 是否已加入训练数据
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)
            
        Returns:
            (记录列表, 总数)
        """
        # 构建WHERE条件
        where_conditions = []
        params = {}
        
        if is_thumb_up is not None:
            where_conditions.append("is_thumb_up = :is_thumb_up")
            params['is_thumb_up'] = is_thumb_up
        
        if create_time_start:
            where_conditions.append("create_time >= :create_time_start")
            params['create_time_start'] = create_time_start
        
        if create_time_end:
            where_conditions.append("create_time <= :create_time_end")
            params['create_time_end'] = create_time_end
        
        if is_in_training_data is not None:
            where_conditions.append("is_in_training_data = :is_in_training_data")
            params['is_in_training_data'] = is_in_training_data
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # 验证排序参数
        valid_sort_fields = ['id', 'create_time', 'update_time', 'user_id']
        if sort_by not in valid_sort_fields:
            sort_by = 'create_time'
        
        if sort_order.lower() not in ['asc', 'desc']:
            sort_order = 'desc'
        
        # 计算OFFSET
        offset = (page - 1) * page_size
        
        # 查询数据
        query_sql = f"""
        SELECT id, question, sql, is_thumb_up, user_id, create_time, 
               is_in_training_data, update_time
        FROM qa_feedback
        {where_clause}
        ORDER BY {sort_by} {sort_order.upper()}
        LIMIT :limit OFFSET :offset
        """
        
        # 查询总数
        count_sql = f"""
        SELECT COUNT(*) as total
        FROM qa_feedback
        {where_clause}
        """
        
        try:
            with self.engine.connect() as conn:
                # 查询数据
                params.update({'limit': page_size, 'offset': offset})
                result = conn.execute(text(query_sql), params)
                records = []
                
                for row in result:
                    records.append({
                        'id': row.id,
                        'question': row.question,
                        'sql': row.sql,
                        'is_thumb_up': row.is_thumb_up,
                        'user_id': row.user_id,
                        'create_time': row.create_time.isoformat() if row.create_time else None,
                        'is_in_training_data': row.is_in_training_data,
                        'update_time': row.update_time.isoformat() if row.update_time else None
                    })
                
                # 查询总数
                count_result = conn.execute(text(count_sql), {k: v for k, v in params.items() if k not in ['limit', 'offset']})
                total = count_result.fetchone().total
                
            return records, total
            
        except Exception as e:
            print(f"[ERROR] 查询反馈记录失败: {e}")
            raise
    
    def delete_feedback(self, feedback_id: int) -> bool:
        """删除反馈记录
        
        Args:
            feedback_id: 反馈记录ID
            
        Returns:
            删除是否成功
        """
        delete_sql = "DELETE FROM qa_feedback WHERE id = :id"
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    result = conn.execute(text(delete_sql), {'id': feedback_id})
                
                if result.rowcount > 0:
                    print(f"[QAFeedbackManager] 反馈记录删除成功, ID: {feedback_id}")
                    return True
                else:
                    print(f"[WARNING] 反馈记录不存在, ID: {feedback_id}")
                    return False
                    
        except Exception as e:
            print(f"[ERROR] 删除反馈记录失败: {e}")
            raise
    
    def update_feedback(self, feedback_id: int, **kwargs) -> bool:
        """更新反馈记录
        
        Args:
            feedback_id: 反馈记录ID
            **kwargs: 要更新的字段
            
        Returns:
            更新是否成功
        """
        # 允许更新的字段
        allowed_fields = ['question', 'sql', 'is_thumb_up', 'user_id', 'is_in_training_data']
        
        update_fields = []
        params = {'id': feedback_id, 'update_time': datetime.now()}
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = :{field}")
                params[field] = value
        
        if not update_fields:
            print("[WARNING] 没有有效的更新字段")
            return False
        
        update_fields.append("update_time = :update_time")
        
        update_sql = f"""
        UPDATE qa_feedback 
        SET {', '.join(update_fields)}
        WHERE id = :id
        """
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    result = conn.execute(text(update_sql), params)
                
                if result.rowcount > 0:
                    print(f"[QAFeedbackManager] 反馈记录更新成功, ID: {feedback_id}")
                    return True
                else:
                    print(f"[WARNING] 反馈记录不存在或无变化, ID: {feedback_id}")
                    return False
                    
        except Exception as e:
            print(f"[ERROR] 更新反馈记录失败: {e}")
            raise
    
    def get_feedback_by_ids(self, feedback_ids: List[int]) -> List[Dict]:
        """根据ID列表获取反馈记录
        
        Args:
            feedback_ids: 反馈记录ID列表
            
        Returns:
            反馈记录列表
        """
        if not feedback_ids:
            return []
        
        # 构建IN查询
        placeholders = ','.join([f':id_{i}' for i in range(len(feedback_ids))])
        params = {f'id_{i}': feedback_id for i, feedback_id in enumerate(feedback_ids)}
        
        query_sql = f"""
        SELECT id, question, sql, is_thumb_up, user_id, create_time, 
               is_in_training_data, update_time
        FROM qa_feedback
        WHERE id IN ({placeholders})
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query_sql), params)
                records = []
                
                for row in result:
                    records.append({
                        'id': row.id,
                        'question': row.question,
                        'sql': row.sql,
                        'is_thumb_up': row.is_thumb_up,
                        'user_id': row.user_id,
                        'create_time': row.create_time,
                        'is_in_training_data': row.is_in_training_data,
                        'update_time': row.update_time
                    })
                
                return records
                
        except Exception as e:
            print(f"[ERROR] 根据ID查询反馈记录失败: {e}")
            raise
    
    def mark_training_status(self, feedback_ids: List[int], status: bool = True) -> int:
        """批量标记训练状态
        
        Args:
            feedback_ids: 反馈记录ID列表
            status: 训练状态
            
        Returns:
            更新的记录数
        """
        if not feedback_ids:
            return 0
        
        placeholders = ','.join([f':id_{i}' for i in range(len(feedback_ids))])
        params = {f'id_{i}': feedback_id for i, feedback_id in enumerate(feedback_ids)}
        params['status'] = status
        params['update_time'] = datetime.now()
        
        update_sql = f"""
        UPDATE qa_feedback 
        SET is_in_training_data = :status, update_time = :update_time
        WHERE id IN ({placeholders})
        """
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    result = conn.execute(text(update_sql), params)
                
                print(f"[QAFeedbackManager] 批量更新训练状态成功, 影响行数: {result.rowcount}")
                return result.rowcount
                
        except Exception as e:
            print(f"[ERROR] 批量更新训练状态失败: {e}")
            raise