import random
from typing import List, Dict, Any
from schema_tools.tools.base import BaseTool, ToolRegistry
from schema_tools.utils.data_structures import ProcessingResult, TableProcessingContext, TableMetadata

@ToolRegistry.register("data_sampler")
class DataSamplerTool(BaseTool):
    """数据采样工具"""
    
    needs_llm = False
    tool_name = "数据采样器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db_connection = kwargs.get('db_connection')
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行数据采样"""
        try:
            from schema_tools.config import SCHEMA_TOOLS_CONFIG
            
            table_metadata = context.table_metadata
            sample_limit = SCHEMA_TOOLS_CONFIG["sample_data_limit"]
            large_table_threshold = SCHEMA_TOOLS_CONFIG["large_table_threshold"]
            
            # 判断是否为大表，使用不同的采样策略
            if table_metadata.row_count and table_metadata.row_count > large_table_threshold:
                sample_data = await self._smart_sample_large_table(table_metadata, sample_limit)
                self.logger.info(f"大表 {table_metadata.full_name} 使用智能采样策略")
            else:
                sample_data = await self._simple_sample(table_metadata, sample_limit)
            
            # 更新上下文中的采样数据
            context.table_metadata.sample_data = sample_data
            
            return ProcessingResult(
                success=True,
                data={
                    'sample_count': len(sample_data),
                    'sampling_strategy': 'smart' if table_metadata.row_count and table_metadata.row_count > large_table_threshold else 'simple'
                },
                metadata={'tool': self.tool_name}
            )
            
        except Exception as e:
            self.logger.exception(f"数据采样失败")
            return ProcessingResult(
                success=False,
                error_message=f"数据采样失败: {str(e)}"
            )
    
    async def _simple_sample(self, table_metadata: TableMetadata, limit: int) -> List[Dict[str, Any]]:
        """简单采样策略"""
        from schema_tools.tools.database_inspector import DatabaseInspectorTool
        
        # 复用数据库检查工具的连接
        inspector = ToolRegistry.get_tool("database_inspector")
        
        query = f"SELECT * FROM {table_metadata.full_name} LIMIT {limit}"
        
        async with inspector.connection_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    async def _smart_sample_large_table(self, table_metadata: TableMetadata, limit: int) -> List[Dict[str, Any]]:
        """智能采样策略（用于大表）"""
        from schema_tools.tools.database_inspector import DatabaseInspectorTool
        
        inspector = ToolRegistry.get_tool("database_inspector")
        samples_per_section = max(1, limit // 3)
        
        samples = []
        
        async with inspector.connection_pool.acquire() as conn:
            # 1. 前N行采样
            front_query = f"SELECT * FROM {table_metadata.full_name} LIMIT {samples_per_section}"
            front_rows = await conn.fetch(front_query)
            samples.extend([dict(row) for row in front_rows])
            
            # 2. 随机中间采样（使用TABLESAMPLE）
            if table_metadata.row_count > samples_per_section * 2:
                try:
                    # 计算采样百分比
                    sample_percent = min(1.0, (samples_per_section * 100.0) / table_metadata.row_count)
                    middle_query = f"""
                    SELECT * FROM {table_metadata.full_name} 
                    TABLESAMPLE SYSTEM({sample_percent}) 
                    LIMIT {samples_per_section}
                    """
                    middle_rows = await conn.fetch(middle_query)
                    samples.extend([dict(row) for row in middle_rows])
                except Exception as e:
                    self.logger.warning(f"TABLESAMPLE采样失败，使用OFFSET采样: {e}")
                    # 回退到OFFSET采样
                    offset = random.randint(samples_per_section, table_metadata.row_count - samples_per_section)
                    offset_query = f"SELECT * FROM {table_metadata.full_name} OFFSET {offset} LIMIT {samples_per_section}"
                    offset_rows = await conn.fetch(offset_query)
                    samples.extend([dict(row) for row in offset_rows])
            
            # 3. 后N行采样
            remaining = limit - len(samples)
            if remaining > 0:
                # 使用ORDER BY ... DESC来获取最后的行
                tail_query = f"""
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER() as rn 
                    FROM {table_metadata.full_name}
                ) sub 
                WHERE sub.rn > (SELECT COUNT(*) FROM {table_metadata.full_name}) - {remaining}
                ORDER BY sub.rn
                """
                try:
                    tail_rows = await conn.fetch(tail_query)
                    # 移除ROW_NUMBER列
                    for row in tail_rows:
                        row_dict = dict(row)
                        row_dict.pop('rn', None)
                        samples.append(row_dict)
                except Exception as e:
                    self.logger.warning(f"尾部采样失败: {e}")
        
        return samples[:limit]  # 确保不超过限制