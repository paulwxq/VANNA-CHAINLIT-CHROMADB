import asyncio
import asyncpg
from typing import List, Dict, Any, Optional
from schema_tools.tools.base import BaseTool, ToolRegistry
from schema_tools.utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo, TableMetadata

@ToolRegistry.register("database_inspector")
class DatabaseInspectorTool(BaseTool):
    """数据库元数据检查工具"""
    
    needs_llm = False
    tool_name = "数据库检查器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db_connection = kwargs.get('db_connection')
        self.connection_pool = None
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行数据库元数据检查"""
        try:
            # 建立数据库连接
            if not self.connection_pool:
                await self._create_connection_pool()
            
            table_name = context.table_metadata.table_name
            schema_name = context.table_metadata.schema_name
            
            # 获取表的基本信息
            table_info = await self._get_table_info(schema_name, table_name)
            if not table_info:
                return ProcessingResult(
                    success=False,
                    error_message=f"表 {schema_name}.{table_name} 不存在或无权限访问"
                )
            
            # 获取字段信息
            fields = await self._get_table_fields(schema_name, table_name)
            
            # 获取表注释
            table_comment = await self._get_table_comment(schema_name, table_name)
            
            # 获取表统计信息
            stats = await self._get_table_statistics(schema_name, table_name)
            
            # 更新表元数据
            context.table_metadata.original_comment = table_comment
            context.table_metadata.comment = table_comment
            context.table_metadata.fields = fields
            context.table_metadata.row_count = stats.get('row_count')
            context.table_metadata.table_size = stats.get('table_size')
            
            return ProcessingResult(
                success=True,
                data={
                    'fields_count': len(fields),
                    'table_comment': table_comment,
                    'row_count': stats.get('row_count'),
                    'table_size': stats.get('table_size')
                },
                metadata={'tool': self.tool_name}
            )
            
        except Exception as e:
            self.logger.exception(f"数据库检查失败")
            return ProcessingResult(
                success=False,
                error_message=f"数据库检查失败: {str(e)}"
            )
    
    async def _create_connection_pool(self):
        """创建数据库连接池"""
        try:
            self.connection_pool = await asyncpg.create_pool(
                self.db_connection,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
            self.logger.info("数据库连接池创建成功")
        except Exception as e:
            self.logger.error(f"创建数据库连接池失败: {e}")
            raise
    
    async def _get_table_info(self, schema_name: str, table_name: str) -> Optional[Dict]:
        """获取表基本信息"""
        query = """
        SELECT schemaname, tablename, tableowner, tablespace, hasindexes, hasrules, hastriggers
        FROM pg_tables 
        WHERE schemaname = $1 AND tablename = $2
        """
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchrow(query, schema_name, table_name)
            return dict(result) if result else None
    
    async def _get_table_fields(self, schema_name: str, table_name: str) -> List[FieldInfo]:
        """获取表字段信息"""
        query = """
        SELECT 
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            pd.description as column_comment,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
            CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key
        FROM information_schema.columns c
        LEFT JOIN pg_description pd ON pd.objsubid = c.ordinal_position 
            AND pd.objoid = (
                SELECT oid FROM pg_class 
                WHERE relname = c.table_name 
                AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = c.table_schema)
            )
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.table_schema = $1 AND tc.table_name = $2 AND tc.constraint_type = 'PRIMARY KEY'
        ) pk ON pk.column_name = c.column_name
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.table_schema = $1 AND tc.table_name = $2 AND tc.constraint_type = 'FOREIGN KEY'
        ) fk ON fk.column_name = c.column_name
        WHERE c.table_schema = $1 AND c.table_name = $2
        ORDER BY c.ordinal_position
        """
        
        fields = []
        async with self.connection_pool.acquire() as conn:
            rows = await conn.fetch(query, schema_name, table_name)
            
            for row in rows:
                field = FieldInfo(
                    name=row['column_name'],
                    type=row['data_type'],
                    nullable=row['is_nullable'] == 'YES',
                    default_value=row['column_default'],
                    original_comment=row['column_comment'],
                    comment=row['column_comment'],
                    is_primary_key=row['is_primary_key'],
                    is_foreign_key=row['is_foreign_key'],
                    max_length=row['character_maximum_length'],
                    precision=row['numeric_precision'],
                    scale=row['numeric_scale']
                )
                fields.append(field)
        
        return fields
    
    async def _get_table_comment(self, schema_name: str, table_name: str) -> Optional[str]:
        """获取表注释"""
        query = """
        SELECT obj_description(oid) as table_comment
        FROM pg_class 
        WHERE relname = $2 
        AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $1)
        """
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchval(query, schema_name, table_name)
            return result
    
    async def _get_table_statistics(self, schema_name: str, table_name: str) -> Dict[str, Any]:
        """获取表统计信息"""
        stats_query = """
        SELECT 
            schemaname,
            tablename,
            attname,
            n_distinct,
            most_common_vals,
            most_common_freqs,
            histogram_bounds
        FROM pg_stats 
        WHERE schemaname = $1 AND tablename = $2
        """
        
        size_query = """
        SELECT pg_size_pretty(pg_total_relation_size($1::oid)) as table_size,
               pg_relation_size($1::oid) as table_size_bytes
        """
        
        count_query = f"SELECT COUNT(*) as row_count FROM {schema_name}.{table_name}"
        
        stats = {}
        async with self.connection_pool.acquire() as conn:
            try:
                # 获取行数
                row_count = await conn.fetchval(count_query)
                stats['row_count'] = row_count
                
                # 获取表大小
                table_oid = await conn.fetchval(
                    "SELECT oid FROM pg_class WHERE relname = $1 AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $2)",
                    table_name, schema_name
                )
                if table_oid:
                    # 确保 table_oid 作为整数传递
                    size_result = await conn.fetchrow(size_query, int(table_oid))
                    stats['table_size'] = size_result['table_size']
                    stats['table_size_bytes'] = size_result['table_size_bytes']
                
            except Exception as e:
                self.logger.warning(f"获取表统计信息失败: {e}")
        
        return stats