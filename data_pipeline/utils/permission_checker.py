from typing import Dict, Optional
import asyncio
from core.logging import get_data_pipeline_logger

class DatabasePermissionChecker:
    """数据库权限检查器"""
    
    def __init__(self, db_inspector):
        self.db_inspector = db_inspector
        self.logger = get_data_pipeline_logger("DatabasePermissionChecker")
        self._permission_cache: Optional[Dict[str, bool]] = None
    
    async def check_permissions(self) -> Dict[str, bool]:
        """
        检查数据库权限
        
        Returns:
            权限字典，包含:
            - connect: 是否可连接
            - select_metadata: 是否可查询元数据
            - select_data: 是否可查询数据
            - is_readonly: 是否为只读
        """
        if self._permission_cache is not None:
            return self._permission_cache
        
        permissions = {
            'connect': False,
            'select_metadata': False,
            'select_data': False,
            'is_readonly': False
        }
        
        try:
            # 检查连接权限
            if await self._test_connection():
                permissions['connect'] = True
                self.logger.info("✓ 数据库连接成功")
            else:
                self.logger.error("✗ 无法连接到数据库")
                return permissions
            
            # 检查元数据查询权限
            if await self._test_metadata_access():
                permissions['select_metadata'] = True
                self.logger.info("✓ 元数据查询权限正常")
            else:
                self.logger.warning("⚠ 元数据查询权限受限")
            
            # 检查数据查询权限
            if await self._test_data_access():
                permissions['select_data'] = True
                self.logger.info("✓ 数据查询权限正常")
            else:
                self.logger.warning("⚠ 数据查询权限受限")
            
            # 检查是否为只读库
            if await self._test_write_permission():
                permissions['is_readonly'] = False
                self.logger.info("✓ 数据库可读写")
            else:
                permissions['is_readonly'] = True
                self.logger.info("ℹ 数据库为只读模式")
            
            self._permission_cache = permissions
            return permissions
            
        except Exception as e:
            self.logger.exception(f"权限检查失败: {e}")
            return permissions
    
    async def _test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            # 尝试获取数据库版本
            query = "SELECT version()"
            async with self.db_inspector.connection_pool.acquire() as conn:
                version = await conn.fetchval(query)
                self.logger.debug(f"数据库版本: {version}")
                return True
        except Exception as e:
            self.logger.error(f"连接测试失败: {e}")
            return False
    
    async def _test_metadata_access(self) -> bool:
        """测试元数据访问权限"""
        try:
            query = """
            SELECT schemaname, tablename 
            FROM pg_tables 
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            LIMIT 1
            """
            async with self.db_inspector.connection_pool.acquire() as conn:
                result = await conn.fetch(query)
                return True
        except Exception as e:
            self.logger.error(f"元数据访问测试失败: {e}")
            return False
    
    async def _test_data_access(self) -> bool:
        """测试数据访问权限"""
        try:
            # 尝试查询一个简单的数据
            query = "SELECT 1 as test"
            async with self.db_inspector.connection_pool.acquire() as conn:
                result = await conn.fetchval(query)
                return result == 1
        except Exception as e:
            self.logger.error(f"数据访问测试失败: {e}")
            return False
    
    async def _test_write_permission(self) -> bool:
        """测试写入权限（通过创建临时表）"""
        try:
            async with self.db_inspector.connection_pool.acquire() as conn:
                # 开启事务
                async with conn.transaction():
                    # 尝试创建临时表
                    await conn.execute("""
                        CREATE TEMP TABLE _schema_tools_permission_test (
                            id INTEGER PRIMARY KEY,
                            test_value TEXT
                        )
                    """)
                    
                    # 尝试插入数据
                    await conn.execute("""
                        INSERT INTO _schema_tools_permission_test (id, test_value) 
                        VALUES (1, 'test')
                    """)
                    
                    # 清理（事务结束时临时表会自动删除）
                    await conn.execute("DROP TABLE IF EXISTS _schema_tools_permission_test")
                    
                return True
        except Exception as e:
            # 写入失败通常意味着只读权限
            self.logger.debug(f"写入权限测试失败（可能是只读库）: {e}")
            return False
    
    def get_permission_summary(self) -> str:
        """获取权限摘要信息"""
        if self._permission_cache is None:
            return "权限未检查"
        
        perms = self._permission_cache
        
        if not perms['connect']:
            return "❌ 无法连接到数据库"
        
        if perms['select_metadata'] and perms['select_data']:
            mode = "只读" if perms['is_readonly'] else "读写"
            return f"✅ 权限正常（{mode}模式）"
        elif perms['select_metadata']:
            return "⚠️ 仅有元数据查询权限"
        else:
            return "❌ 权限不足"
    
    def require_minimum_permissions(self) -> bool:
        """检查是否满足最低权限要求"""
        if self._permission_cache is None:
            return False
        
        # 最低要求：能连接和查询元数据
        return (self._permission_cache['connect'] and 
                self._permission_cache['select_metadata'])