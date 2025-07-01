from typing import List, Set
from data_pipeline.config import SCHEMA_TOOLS_CONFIG
import logging

class SystemTableFilter:
    """系统表过滤器"""
    
    # PostgreSQL系统表前缀
    PG_SYSTEM_PREFIXES = [
        'pg_', 'information_schema', 'sql_', 'cardinal_number',
        'character_data', 'sql_identifier', 'time_stamp', 'yes_or_no'
    ]
    
    # 系统schema
    SYSTEM_SCHEMAS = [
        'information_schema', 'pg_catalog', 'pg_toast', 
        'pg_temp_1', 'pg_toast_temp_1', 'pg_temp', 'pg_toast_temp'
    ]
    
    def __init__(self):
        self.logger = logging.getLogger("SystemTableFilter")
        
        # 加载自定义配置
        self.custom_prefixes = SCHEMA_TOOLS_CONFIG.get("custom_system_prefixes", [])
        self.custom_schemas = SCHEMA_TOOLS_CONFIG.get("custom_system_schemas", [])
    
    def is_system_table(self, schema_name: str, table_name: str) -> bool:
        """
        判断是否为系统表
        
        Args:
            schema_name: Schema名称
            table_name: 表名
            
        Returns:
            是否为系统表
        """
        # 检查系统schema
        all_system_schemas = self.SYSTEM_SCHEMAS + self.custom_schemas
        if schema_name.lower() in [s.lower() for s in all_system_schemas]:
            return True
        
        # 检查表名前缀
        table_lower = table_name.lower()
        all_prefixes = self.PG_SYSTEM_PREFIXES + self.custom_prefixes
        
        for prefix in all_prefixes:
            if table_lower.startswith(prefix.lower()):
                return True
        
        # 检查临时表模式
        if schema_name.lower().startswith('pg_temp') or schema_name.lower().startswith('pg_toast_temp'):
            return True
        
        return False
    
    def filter_user_tables(self, table_list: List[str]) -> List[str]:
        """
        过滤出用户表
        
        Args:
            table_list: 表名列表（可能包含schema）
            
        Returns:
            用户表列表
        """
        user_tables = []
        filtered_tables = []
        
        for table_spec in table_list:
            # 解析schema和表名
            if '.' in table_spec:
                schema, table = table_spec.split('.', 1)
            else:
                schema, table = 'public', table_spec
            
            if self.is_system_table(schema, table):
                filtered_tables.append(table_spec)
                self.logger.debug(f"过滤系统表: {table_spec}")
            else:
                user_tables.append(table_spec)
        
        if filtered_tables:
            self.logger.info(f"过滤了 {len(filtered_tables)} 个系统表，保留 {len(user_tables)} 个用户表")
            if len(filtered_tables) <= 10:
                self.logger.debug(f"被过滤的系统表: {', '.join(filtered_tables)}")
        
        return user_tables
    
    def get_system_prefixes(self) -> Set[str]:
        """获取所有系统表前缀"""
        return set(self.PG_SYSTEM_PREFIXES + self.custom_prefixes)
    
    def get_system_schemas(self) -> Set[str]:
        """获取所有系统schema"""
        return set(self.SYSTEM_SCHEMAS + self.custom_schemas)
    
    def add_custom_prefix(self, prefix: str):
        """添加自定义系统表前缀"""
        if prefix not in self.custom_prefixes:
            self.custom_prefixes.append(prefix)
            self.logger.info(f"添加自定义系统表前缀: {prefix}")
    
    def add_custom_schema(self, schema: str):
        """添加自定义系统schema"""
        if schema not in self.custom_schemas:
            self.custom_schemas.append(schema)
            self.logger.info(f"添加自定义系统schema: {schema}")