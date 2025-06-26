import logging
import random
from typing import List, Dict, Any, Optional
from data_pipeline.config import SCHEMA_TOOLS_CONFIG

class LargeTableHandler:
    """大表处理策略"""
    
    def __init__(self):
        self.logger = logging.getLogger("schema_tools.LargeTableHandler")
        self.large_table_threshold = SCHEMA_TOOLS_CONFIG.get("large_table_threshold", 1000000)
        self.skip_large_tables = SCHEMA_TOOLS_CONFIG.get("skip_large_tables", False)
        self.max_table_size = SCHEMA_TOOLS_CONFIG.get("max_table_size", 10000000)
    
    def should_skip_table(self, row_count: Optional[int]) -> bool:
        """
        判断是否应跳过表
        
        Args:
            row_count: 表行数
            
        Returns:
            是否跳过
        """
        if not self.skip_large_tables or row_count is None:
            return False
        
        if row_count > self.max_table_size:
            self.logger.warning(f"表行数({row_count})超过最大限制({self.max_table_size})，将跳过处理")
            return True
        
        return False
    
    def is_large_table(self, row_count: Optional[int]) -> bool:
        """
        判断是否为大表
        
        Args:
            row_count: 表行数
            
        Returns:
            是否为大表
        """
        if row_count is None:
            return False
        
        return row_count > self.large_table_threshold
    
    async def get_smart_sample(self, db_inspector, table_name: str, schema_name: str, 
                               row_count: Optional[int], limit: int = 20) -> List[Dict[str, Any]]:
        """
        智能采样策略
        
        Args:
            db_inspector: 数据库检查工具实例
            table_name: 表名
            schema_name: Schema名
            row_count: 表行数
            limit: 采样数量限制
            
        Returns:
            采样数据列表
        """
        full_table_name = f"{schema_name}.{table_name}"
        
        # 如果不是大表，使用简单采样
        if not self.is_large_table(row_count):
            return await self._simple_sample(db_inspector, full_table_name, limit)
        
        self.logger.info(f"表 {full_table_name} 有 {row_count} 行，使用智能采样策略")
        
        # 大表使用分层采样
        return await self._stratified_sample(db_inspector, full_table_name, row_count, limit)
    
    async def _simple_sample(self, db_inspector, full_table_name: str, limit: int) -> List[Dict[str, Any]]:
        """简单采样策略"""
        query = f"SELECT * FROM {full_table_name} LIMIT {limit}"
        
        async with db_inspector.connection_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    async def _stratified_sample(self, db_inspector, full_table_name: str, 
                                  row_count: int, limit: int) -> List[Dict[str, Any]]:
        """分层采样策略（用于大表）"""
        samples_per_section = max(1, limit // 3)
        samples = []
        
        async with db_inspector.connection_pool.acquire() as conn:
            # 1. 前N行采样
            front_query = f"SELECT * FROM {full_table_name} LIMIT {samples_per_section}"
            front_rows = await conn.fetch(front_query)
            samples.extend([dict(row) for row in front_rows])
            
            # 2. 随机中间采样
            if row_count > samples_per_section * 2:
                try:
                    # 使用TABLESAMPLE进行随机采样
                    sample_percent = min(1.0, (samples_per_section * 100.0) / row_count)
                    middle_query = f"""
                    SELECT * FROM {full_table_name} 
                    TABLESAMPLE SYSTEM({sample_percent}) 
                    LIMIT {samples_per_section}
                    """
                    middle_rows = await conn.fetch(middle_query)
                    samples.extend([dict(row) for row in middle_rows])
                except Exception as e:
                    self.logger.warning(f"TABLESAMPLE采样失败，使用OFFSET采样: {e}")
                    # 回退到OFFSET采样
                    offset = random.randint(samples_per_section, row_count - samples_per_section)
                    offset_query = f"SELECT * FROM {full_table_name} OFFSET {offset} LIMIT {samples_per_section}"
                    offset_rows = await conn.fetch(offset_query)
                    samples.extend([dict(row) for row in offset_rows])
            
            # 3. 后N行采样
            remaining = limit - len(samples)
            if remaining > 0 and row_count > limit:
                # 使用OFFSET获取最后的行
                offset = max(0, row_count - remaining)
                tail_query = f"SELECT * FROM {full_table_name} OFFSET {offset} LIMIT {remaining}"
                tail_rows = await conn.fetch(tail_query)
                samples.extend([dict(row) for row in tail_rows])
        
        self.logger.info(f"智能采样完成，获取了 {len(samples)} 条数据")
        return samples[:limit]  # 确保不超过限制
    
    def get_sampling_strategy_info(self, row_count: Optional[int]) -> Dict[str, Any]:
        """
        获取采样策略信息
        
        Args:
            row_count: 表行数
            
        Returns:
            策略信息字典
        """
        if row_count is None:
            return {
                'strategy': 'simple',
                'reason': '未知表大小',
                'is_large_table': False
            }
        
        if self.should_skip_table(row_count):
            return {
                'strategy': 'skip',
                'reason': f'表太大({row_count}行)，超过限制({self.max_table_size}行)',
                'is_large_table': True
            }
        
        if self.is_large_table(row_count):
            return {
                'strategy': 'smart',
                'reason': f'大表({row_count}行)，使用智能采样',
                'is_large_table': True
            }
        
        return {
            'strategy': 'simple',
            'reason': f'普通表({row_count}行)，使用简单采样',
            'is_large_table': False
        }