import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from data_pipeline.config import SCHEMA_TOOLS_CONFIG
import logging


@dataclass
class SQLValidationResult:
    """SQL验证结果"""
    sql: str
    valid: bool
    error_message: str = ""
    execution_time: float = 0.0
    retry_count: int = 0
    
    # SQL修复相关字段
    repair_attempted: bool = False
    repair_successful: bool = False
    repaired_sql: str = ""
    repair_error: str = ""


@dataclass
class ValidationStats:
    """验证统计信息"""
    total_sqls: int = 0
    valid_sqls: int = 0
    invalid_sqls: int = 0
    total_time: float = 0.0
    avg_time_per_sql: float = 0.0
    retry_count: int = 0
    
    # SQL修复统计
    repair_attempted: int = 0
    repair_successful: int = 0
    repair_failed: int = 0


class SQLValidator:
    """SQL验证器"""
    
    def __init__(self, db_connection: str = None):
        """
        初始化SQL验证器
        
        Args:
            db_connection: 数据库连接字符串（可选，用于复用连接池）
        """
        self.db_connection = db_connection
        self.connection_pool = None
        self.config = SCHEMA_TOOLS_CONFIG['sql_validation']
        self.logger = logging.getLogger("SQLValidator")
        
    async def _get_connection_pool(self):
        """获取或创建连接池"""
        if not self.connection_pool:
            if self.db_connection:
                # 直接创建自己的连接池，避免复用问题
                import asyncpg
                try:
                    self.connection_pool = await asyncpg.create_pool(
                        self.db_connection,
                        min_size=1,
                        max_size=5,
                        command_timeout=30
                    )
                    self.logger.info("SQL验证器连接池创建成功")
                except Exception as e:
                    self.logger.error(f"创建SQL验证器连接池失败: {e}")
                    raise
            else:
                raise ValueError("需要提供数据库连接字符串")
        
        return self.connection_pool
    
    async def validate_sql(self, sql: str, retry_count: int = 0) -> SQLValidationResult:
        """
        验证单个SQL语句
        
        Args:
            sql: 要验证的SQL语句
            retry_count: 当前重试次数
            
        Returns:
            SQLValidationResult: 验证结果
        """
        start_time = time.time()
        
        try:
            pool = await self._get_connection_pool()
            
            async with pool.acquire() as conn:
                # 设置超时
                timeout = self.config['validation_timeout']
                
                # 设置只读模式（安全考虑）
                if self.config['readonly_mode']:
                    await asyncio.wait_for(
                        conn.execute("SET default_transaction_read_only = on"),
                        timeout=timeout
                    )
                
                # 执行EXPLAIN验证SQL
                await asyncio.wait_for(
                    conn.execute(f"EXPLAIN {sql}"),
                    timeout=timeout
                )
                
                execution_time = time.time() - start_time
                
                self.logger.debug(f"SQL验证成功: {sql[:50]}... ({execution_time:.3f}s)")
                
                return SQLValidationResult(
                    sql=sql,
                    valid=True,
                    execution_time=execution_time,
                    retry_count=retry_count
                )
                
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"验证超时({self.config['validation_timeout']}秒)"
            
            self.logger.warning(f"SQL验证超时: {sql[:50]}...")
            
            return SQLValidationResult(
                sql=sql,
                valid=False,
                error_message=error_msg,
                execution_time=execution_time,
                retry_count=retry_count
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            
            # 检查是否需要重试
            max_retries = self.config['max_retry_count']
            if retry_count < max_retries and self._should_retry(e):
                self.logger.debug(f"SQL验证失败，重试 {retry_count + 1}/{max_retries}: {error_msg}")
                await asyncio.sleep(0.5)  # 短暂等待后重试
                return await self.validate_sql(sql, retry_count + 1)
            
            self.logger.debug(f"SQL验证失败: {sql[:50]}... - {error_msg}")
            
            return SQLValidationResult(
                sql=sql,
                valid=False,
                error_message=error_msg,
                execution_time=execution_time,
                retry_count=retry_count
            )
    
    async def validate_sqls_batch(self, sqls: List[str]) -> List[SQLValidationResult]:
        """
        批量验证SQL语句
        
        Args:
            sqls: SQL语句列表
            
        Returns:
            验证结果列表
        """
        if not sqls:
            return []
        
        max_concurrent = self.config['max_concurrent_validations']
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def validate_with_semaphore(sql):
            async with semaphore:
                return await self.validate_sql(sql)
        
        self.logger.info(f"开始批量验证 {len(sqls)} 个SQL语句 (并发度: {max_concurrent})")
        
        # 并发执行验证
        tasks = [validate_with_semaphore(sql) for sql in sqls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        validated_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"SQL验证任务异常: {sqls[i][:50]}... - {result}")
                validated_results.append(SQLValidationResult(
                    sql=sqls[i],
                    valid=False,
                    error_message=f"验证任务异常: {str(result)}"
                ))
            else:
                validated_results.append(result)
        
        return validated_results
    
    def _should_retry(self, error: Exception) -> bool:
        """
        判断是否应该重试
        
        Args:
            error: 异常对象
            
        Returns:
            是否应该重试
        """
        # 一般网络或连接相关的错误可以重试
        retry_indicators = [
            "connection",
            "network",
            "timeout",
            "server closed",
            "pool",
        ]
        
        error_str = str(error).lower()
        return any(indicator in error_str for indicator in retry_indicators)
    
    def calculate_stats(self, results: List[SQLValidationResult]) -> ValidationStats:
        """
        计算验证统计信息
        
        Args:
            results: 验证结果列表
            
        Returns:
            ValidationStats: 统计信息
        """
        total_sqls = len(results)
        valid_sqls = sum(1 for r in results if r.valid)
        invalid_sqls = total_sqls - valid_sqls
        total_time = sum(r.execution_time for r in results)
        avg_time = total_time / total_sqls if total_sqls > 0 else 0.0
        total_retries = sum(r.retry_count for r in results)
        
        # 计算修复统计
        repair_attempted = sum(1 for r in results if r.repair_attempted)
        repair_successful = sum(1 for r in results if r.repair_successful)
        repair_failed = repair_attempted - repair_successful
        
        return ValidationStats(
            total_sqls=total_sqls,
            valid_sqls=valid_sqls,
            invalid_sqls=invalid_sqls,
            total_time=total_time,
            avg_time_per_sql=avg_time,
            retry_count=total_retries,
            repair_attempted=repair_attempted,
            repair_successful=repair_successful,
            repair_failed=repair_failed
        ) 