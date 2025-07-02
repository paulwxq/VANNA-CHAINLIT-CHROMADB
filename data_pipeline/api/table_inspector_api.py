"""
表检查API模块

复用data_pipeline中的数据库连接和查询功能，提供独立的表信息查询API
"""

import asyncio
import asyncpg
import logging
from typing import List, Optional, Dict, Any
from data_pipeline.tools.database_inspector import DatabaseInspectorTool


class TableInspectorAPI:
    """表检查API类，复用现有的数据库功能"""
    
    def __init__(self):
        self.logger = logging.getLogger("TableInspectorAPI")
        self.db_inspector = None
    
    async def get_tables_list(self, db_connection: str, schema: Optional[str] = None) -> List[str]:
        """
        获取数据库表列表
        
        Args:
            db_connection: 完整的PostgreSQL连接字符串
            schema: 可选的schema参数，支持多个schema用逗号分隔
                   如果为None或空字符串，则只返回public schema的表
        
        Returns:
            表名列表，格式为 schema.tablename
        """
        try:
            # 创建数据库检查器实例
            self.db_inspector = DatabaseInspectorTool(db_connection=db_connection)
            
            # 创建连接池
            await self.db_inspector._create_connection_pool()
            
            # 解析schema参数
            target_schemas = self._parse_schemas(schema)
            
            # 查询表列表
            tables = await self._query_tables(target_schemas)
            
            return tables
            
        except Exception as e:
            self.logger.error(f"获取表列表失败: {e}")
            raise
        finally:
            # 清理连接池
            if self.db_inspector and self.db_inspector.connection_pool:
                await self.db_inspector.connection_pool.close()
    
    def _parse_schemas(self, schema: Optional[str]) -> List[str]:
        """
        解析schema参数
        
        Args:
            schema: schema参数，可以是单个schema或逗号分隔的多个schema
        
        Returns:
            schema列表
        """
        if not schema or schema.strip() == "":
            # 如果没有指定schema，默认只查询public schema
            return ["public"]
        
        # 解析逗号分隔的schema
        schemas = [s.strip() for s in schema.split(",") if s.strip()]
        
        # 如果解析后为空，回退到public
        if not schemas:
            return ["public"]
        
        return schemas
    
    async def _query_tables(self, schemas: List[str]) -> List[str]:
        """
        查询指定schema中的表
        
        Args:
            schemas: schema列表
        
        Returns:
            表名列表，格式为 schema.tablename
        """
        tables = []
        
        async with self.db_inspector.connection_pool.acquire() as conn:
            for schema in schemas:
                # 查询指定schema中的表
                query = """
                SELECT schemaname, tablename 
                FROM pg_tables 
                WHERE schemaname = $1
                ORDER BY tablename
                """
                
                rows = await conn.fetch(query, schema)
                
                # 格式化表名为 schema.tablename
                for row in rows:
                    schema_name = row['schemaname']
                    table_name = row['tablename']
                    full_table_name = f"{schema_name}.{table_name}"
                    tables.append(full_table_name)
        
        # 按名称排序
        tables.sort()
        
        self.logger.info(f"查询到 {len(tables)} 个表，schemas: {schemas}")
        
        return tables
    
    async def get_table_ddl(self, db_connection: str, table: str, business_context: str = None, output_type: str = "ddl") -> Dict[str, Any]:
        """
        获取表的DDL语句或MD文档
        
        Args:
            db_connection: 数据库连接字符串
            table: 表名，格式为 schema.tablename
            business_context: 业务上下文描述
            output_type: 输出类型，支持 "ddl", "md", "both"
        
        Returns:
            包含DDL/MD内容的字典
        """
        try:
            # 解析表名
            schema_name, table_name = self._parse_table_name(table)
            
            # 导入必要的模块
            from data_pipeline.tools.database_inspector import DatabaseInspectorTool
            from data_pipeline.tools.comment_generator import CommentGeneratorTool
            from data_pipeline.tools.ddl_generator import DDLGeneratorTool
            from data_pipeline.tools.doc_generator import DocGeneratorTool
            from data_pipeline.tools.data_sampler import DataSamplerTool
            from data_pipeline.utils.data_structures import TableMetadata, TableProcessingContext
            from core.vanna_llm_factory import create_vanna_instance
            
            # 创建数据库检查器实例
            db_inspector = DatabaseInspectorTool(db_connection=db_connection)
            await db_inspector._create_connection_pool()
            
            # 创建表元数据对象
            table_metadata = TableMetadata(
                table_name=table_name,
                schema_name=schema_name,
                full_name=f"{schema_name}.{table_name}",
                fields=[],
                comment=None,
                sample_data=[]
            )
            
            # 获取全局Vanna实例（仅用于LLM调用，不修改其数据库连接）
            from common.vanna_instance import get_vanna_instance
            vn = get_vanna_instance()
            self.logger.info("使用全局Vanna单例实例进行LLM调用（不修改其数据库连接）")
            
            # 创建处理上下文
            context = TableProcessingContext(
                table_metadata=table_metadata,
                business_context=business_context or "数据库管理系统",
                output_dir="/tmp",  # 临时目录，API不会真正写文件
                pipeline="api_direct",  # API直接调用标识
                vn=vn,
                file_manager=None,  # 不需要文件管理器
                step_results={}
            )
            
            # 第1步：获取表结构信息
            self.logger.info(f"开始获取表结构: {table}")
            inspect_result = await db_inspector.execute(context)
            if not inspect_result.success:
                raise Exception(f"获取表结构失败: {inspect_result.error_message}")
            
            # 第2步：获取样例数据（用于生成更好的注释）
            self.logger.info("开始获取样例数据")
            try:
                data_sampler = DataSamplerTool(vn=vn, db_connection=db_connection)
                sample_result = await data_sampler.execute(context)
                if sample_result.success:
                    self.logger.info("样例数据获取成功")
                else:
                    self.logger.warning(f"样例数据获取失败: {sample_result.error_message}")
            except Exception as e:
                self.logger.warning(f"样例数据获取异常: {e}")
            
            # 第3步：生成注释（调用LLM）
            if business_context:
                self.logger.info("开始生成LLM注释")
                try:
                    comment_generator = CommentGeneratorTool(
                        vn=vn,
                        business_context=business_context,
                        db_connection=db_connection
                    )
                    comment_result = await comment_generator.execute(context)
                    if comment_result.success:
                        self.logger.info("LLM注释生成成功")
                    else:
                        self.logger.warning(f"LLM注释生成失败: {comment_result.error_message}")
                except Exception as e:
                    self.logger.warning(f"LLM注释生成异常: {e}")
            
            # 第4步：根据类型生成输出
            result = {}
            
            if output_type in ["ddl", "both"]:
                self.logger.info("开始生成DDL")
                ddl_generator = DDLGeneratorTool()
                ddl_result = await ddl_generator.execute(context)
                if ddl_result.success:
                    result["ddl"] = ddl_result.data.get("ddl_content", "")
                    # 保存DDL结果供MD生成器使用
                    context.step_results["ddl_generator"] = ddl_result
                else:
                    raise Exception(f"DDL生成失败: {ddl_result.error_message}")
            
            if output_type in ["md", "both"]:
                self.logger.info("开始生成MD文档")
                doc_generator = DocGeneratorTool()
                
                # 直接调用MD生成方法，不依赖文件系统
                md_content = doc_generator._generate_md_content(
                    table_metadata, 
                    result.get("ddl", "")
                )
                result["md"] = md_content
            
            # 添加表信息摘要
            result["table_info"] = {
                "table_name": table_metadata.table_name,
                "schema_name": table_metadata.schema_name,
                "full_name": table_metadata.full_name,
                "comment": table_metadata.comment,
                "field_count": len(table_metadata.fields),
                "row_count": table_metadata.row_count,
                "table_size": table_metadata.table_size
            }
            
            # 添加字段信息
            result["fields"] = [
                {
                    "name": field.name,
                    "type": field.type,
                    "nullable": field.nullable,
                    "comment": field.comment,
                    "is_primary_key": field.is_primary_key,
                    "is_foreign_key": field.is_foreign_key,
                    "default_value": field.default_value,
                    "is_enum": getattr(field, 'is_enum', False),
                    "enum_values": getattr(field, 'enum_values', [])
                }
                for field in table_metadata.fields
            ]
            
            self.logger.info(f"表DDL生成完成: {table}, 输出类型: {output_type}")
            return result
            
        except Exception as e:
            self.logger.error(f"获取表DDL失败: {e}")
            raise
        finally:
            # 清理连接池
            if 'db_inspector' in locals() and db_inspector.connection_pool:
                await db_inspector.connection_pool.close()
    
    def _parse_table_name(self, table: str) -> tuple[str, str]:
        """
        解析表名
        
        Args:
            table: 表名，格式为 schema.tablename 或 tablename
        
        Returns:
            (schema_name, table_name) 元组
        """
        if "." in table:
            parts = table.split(".", 1)
            return parts[0], parts[1]
        else:
            # 如果没有指定schema，默认为public
            return "public", table
    
    def _parse_db_connection(self, db_connection: str) -> Dict[str, Any]:
        """
        解析PostgreSQL连接字符串
        
        Args:
            db_connection: PostgreSQL连接字符串，格式为 postgresql://user:password@host:port/dbname
        
        Returns:
            包含数据库连接参数的字典
        """
        import re
        
        # 解析连接字符串的正则表达式
        pattern = r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
        match = re.match(pattern, db_connection)
        
        if not match:
            raise ValueError(f"无效的PostgreSQL连接字符串格式: {db_connection}")
        
        user, password, host, port, dbname = match.groups()
        
        return {
            'user': user,
            'password': password,
            'host': host,
            'port': int(port),
            'dbname': dbname
        } 