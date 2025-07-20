import asyncio
import time
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from data_pipeline.tools.base import ToolRegistry, PipelineExecutor
from data_pipeline.utils.data_structures import TableMetadata, TableProcessingContext, ProcessingResult
from data_pipeline.utils.file_manager import FileNameManager
from data_pipeline.utils.system_filter import SystemTableFilter
from data_pipeline.utils.permission_checker import DatabasePermissionChecker
from data_pipeline.utils.table_parser import TableListParser
from data_pipeline.config import SCHEMA_TOOLS_CONFIG
from data_pipeline.dp_logging import get_logger

class SchemaTrainingDataAgent:
    """Schema训练数据生成AI Agent"""
    
    def __init__(self, 
                 db_connection: str,
                 table_list_file: str,
                 business_context: str = None,
                 output_dir: str = None,
                 task_id: str = None,
                 pipeline: str = "full"):
        
        self.db_connection = db_connection
        self.table_list_file = table_list_file
        self.business_context = business_context or "数据库管理系统"
        self.pipeline = pipeline
        
        # 配置管理
        self.config = SCHEMA_TOOLS_CONFIG
        self.output_dir = output_dir or self.config["output_directory"]
        
        # 初始化组件
        self.file_manager = FileNameManager(self.output_dir)
        self.system_filter = SystemTableFilter()
        self.table_parser = TableListParser()
        self.pipeline_executor = PipelineExecutor(self.config["available_pipelines"])
        
        # 统计信息
        self.stats = {
            'total_tables': 0,
            'processed_tables': 0,
            'failed_tables': 0,
            'skipped_tables': 0,
            'start_time': None,
            'end_time': None
        }
        
        self.failed_tables = []
        self.task_id = task_id
        
        # 初始化独立日志系统
        if task_id:
            self.logger = get_logger("SchemaTrainingDataAgent", task_id)
        else:
            # 脚本模式下，如果没有传递task_id，生成一个
            from datetime import datetime
            self.task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.logger = get_logger("SchemaTrainingDataAgent", self.task_id)
    
    async def generate_training_data(self) -> Dict[str, Any]:
        """主入口：生成训练数据"""
        try:
            self.stats['start_time'] = time.time()
            self.logger.info("🚀 开始生成Schema训练数据")
            
            # 1. 初始化
            await self._initialize()
            
            # 2. 检查数据库权限
            await self._check_database_permissions()
            
            # 3. 解析表清单
            tables = await self._parse_table_list()
            
            # 4. 过滤系统表
            user_tables = self._filter_system_tables(tables)
            
            # 5. 并发处理表
            results = await self._process_tables_concurrently(user_tables)
            
            # 6. 设置结束时间
            self.stats['end_time'] = time.time()
            
            # 7. 生成总结报告
            report = self._generate_summary_report(results)
            
            self.logger.info("✅ Schema训练数据生成完成")
            
            return report
            
        except Exception as e:
            self.stats['end_time'] = time.time()
            self.logger.exception("❌ Schema训练数据生成失败")
            raise
    
    async def _initialize(self):
        """初始化Agent"""
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        if self.config["create_subdirectories"]:
            os.makedirs(os.path.join(self.output_dir, "ddl"), exist_ok=True)
            os.makedirs(os.path.join(self.output_dir, "docs"), exist_ok=True)
        
        # logs目录始终创建
        # os.makedirs(os.path.join(self.output_dir, "logs"), exist_ok=True)
        
        # 初始化数据库工具
        database_tool = ToolRegistry.get_tool("database_inspector", db_connection=self.db_connection)
        await database_tool._create_connection_pool()
        
        self.logger.info(f"初始化完成，输出目录: {self.output_dir}")
    
    async def _check_database_permissions(self):
        """检查数据库权限"""
        if not self.config["check_permissions"]:
            return
        
        inspector = ToolRegistry.get_tool("database_inspector", db_connection=self.db_connection)
        
        # 确保连接池已创建
        if not inspector.connection_pool:
            await inspector._create_connection_pool()
        
        # 解析并打印数据库连接信息
        try:
            db_info = self._parse_db_connection(self.db_connection)
            self.logger.info(f"🔗 数据库连接信息: 用户名={db_info['user']}, 密码={'*' * len(db_info['password'])}, 主机={db_info['host']}:{db_info['port']}, 数据库={db_info['dbname']}")
        except Exception as e:
            self.logger.warning(f"无法解析数据库连接字符串: {e}")
        
        checker = DatabasePermissionChecker(inspector)
        
        permissions = await checker.check_permissions()
        
        if not permissions['connect']:
            raise Exception("无法连接到数据库")
        
        if self.config["require_select_permission"] and not permissions['select_data']:
            if not self.config["allow_readonly_database"]:
                raise Exception("数据库查询权限不足")
            else:
                self.logger.warning("数据库为只读或权限受限，部分功能可能受影响")
        
        self.logger.info(f"数据库权限检查完成: {permissions}")
    
    def _parse_db_connection(self, db_connection: str) -> Dict[str, str]:
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
            'port': port,
            'dbname': dbname
        }
    
    async def _parse_table_list(self) -> List[str]:
        """解析表清单文件"""
        tables = self.table_parser.parse_file(self.table_list_file)
        self.stats['total_tables'] = len(tables)
        self.logger.info(f"📋 从清单文件读取到 {len(tables)} 个表")
        return tables
    
    def _filter_system_tables(self, tables: List[str]) -> List[str]:
        """过滤系统表"""
        if not self.config["filter_system_tables"]:
            return tables
        
        user_tables = self.system_filter.filter_user_tables(tables)
        filtered_count = len(tables) - len(user_tables)
        
        if filtered_count > 0:
            self.logger.info(f"🔍 过滤了 {filtered_count} 个系统表，保留 {len(user_tables)} 个用户表")
            self.stats['skipped_tables'] += filtered_count
        
        return user_tables
    
    async def _process_tables_concurrently(self, tables: List[str]) -> List[Dict[str, Any]]:
        """并发处理表"""
        max_concurrent = self.config["max_concurrent_tables"]
        semaphore = asyncio.Semaphore(max_concurrent)
        
        self.logger.info(f"🔄 开始并发处理 {len(tables)} 个表 (最大并发: {max_concurrent})")
        
        # 创建任务
        tasks = [
            self._process_single_table_with_semaphore(semaphore, table_spec)
            for table_spec in tables
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        successful = sum(1 for r in results if isinstance(r, dict) and r.get('success', False))
        failed = len(results) - successful
        
        self.stats['processed_tables'] = successful
        self.stats['failed_tables'] = failed
        
        self.logger.info(f"📊 处理完成: 成功 {successful} 个，失败 {failed} 个")
        
        return [r for r in results if isinstance(r, dict)]
    
    async def _process_single_table_with_semaphore(self, semaphore: asyncio.Semaphore, table_spec: str) -> Dict[str, Any]:
        """带信号量的单表处理"""
        async with semaphore:
            return await self._process_single_table(table_spec)
    
    async def _process_single_table(self, table_spec: str) -> Dict[str, Any]:
        """处理单个表"""
        start_time = time.time()
        
        try:
            # 解析表名
            if '.' in table_spec:
                schema_name, table_name = table_spec.split('.', 1)
            else:
                schema_name, table_name = 'public', table_spec
            
            full_name = f"{schema_name}.{table_name}"
            self.logger.info(f"🔍 开始处理表: {full_name}")
            
            # 创建表元数据
            table_metadata = TableMetadata(
                schema_name=schema_name,
                table_name=table_name,
                full_name=full_name
            )
            
            # 创建处理上下文
            context = TableProcessingContext(
                table_metadata=table_metadata,
                business_context=self.business_context,
                output_dir=self.output_dir,
                pipeline=self.pipeline,
                vn=None,  # 将在工具中注入
                file_manager=self.file_manager,
                db_connection=self.db_connection,  # 添加数据库连接参数
                start_time=start_time
            )
            
            # 执行处理链
            step_results = await self.pipeline_executor.execute_pipeline(self.pipeline, context)
            
            # 计算总体成功状态
            success = all(result.success for result in step_results.values())
            
            execution_time = time.time() - start_time
            
            if success:
                self.logger.info(f"✅ 表 {full_name} 处理成功，耗时: {execution_time:.2f}秒")
            else:
                self.logger.error(f"❌ 表 {full_name} 处理失败，耗时: {execution_time:.2f}秒")
                self.failed_tables.append(full_name)
            
            return {
                'success': success,
                'table_name': full_name,
                'execution_time': execution_time,
                'step_results': {k: v.to_dict() for k, v in step_results.items()},
                'metadata': {
                    'fields_count': len(table_metadata.fields),
                    'row_count': table_metadata.row_count,
                    'enum_fields': len([f for f in table_metadata.fields if f.is_enum])
                }
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"表 {table_spec} 处理异常: {str(e)}"
            self.logger.exception(error_msg)
            self.failed_tables.append(table_spec)
            
            return {
                'success': False,
                'table_name': table_spec,
                'execution_time': execution_time,
                'error_message': error_msg,
                'step_results': {}
            }
    
    def _generate_summary_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成总结报告"""
        total_time = self.stats['end_time'] - self.stats['start_time']
        
        # 计算统计信息
        successful_results = [r for r in results if r.get('success', False)]
        failed_results = [r for r in results if not r.get('success', False)]
        
        total_fields = sum(r.get('metadata', {}).get('fields_count', 0) for r in successful_results)
        total_enum_fields = sum(r.get('metadata', {}).get('enum_fields', 0) for r in successful_results)
        
        avg_execution_time = sum(r.get('execution_time', 0) for r in results) / len(results) if results else 0
        
        # 计算生成的文件数量
        successful_count = len(successful_results)
        if self.pipeline == 'full':
            md_files_generated = successful_count
            ddl_files_generated = successful_count
            total_files_generated = successful_count * 2
        elif self.pipeline == 'ddl_only':
            md_files_generated = 0
            ddl_files_generated = successful_count
            total_files_generated = successful_count
        elif self.pipeline == 'analysis_only':
            md_files_generated = successful_count
            ddl_files_generated = 0
            total_files_generated = successful_count
        else:
            md_files_generated = successful_count
            ddl_files_generated = 0
            total_files_generated = successful_count
        
        report = {
            'summary': {
                'total_tables': self.stats['total_tables'],
                'processed_successfully': len(successful_results),
                'failed': len(failed_results),
                'skipped_system_tables': self.stats['skipped_tables'],
                'total_execution_time': total_time,
                'average_table_time': avg_execution_time
            },
            'statistics': {
                'total_fields_processed': total_fields,
                'enum_fields_detected': total_enum_fields,
                'md_files_generated': md_files_generated,
                'ddl_files_generated': ddl_files_generated,
                'total_files_generated': total_files_generated
            },
            'failed_tables': self.failed_tables,
            'detailed_results': results,
            'configuration': {
                'pipeline': self.pipeline,
                'business_context': self.business_context,
                'output_directory': self.output_dir,
                'max_concurrent_tables': self.config['max_concurrent_tables']
            }
        }
        
        # 输出总结
        self.logger.info(f"📊 处理总结:")
        self.logger.info(f"  ✅ 成功: {report['summary']['processed_successfully']} 个表")
        self.logger.info(f"  ❌ 失败: {report['summary']['failed']} 个表")
        self.logger.info(f"  ⏭️  跳过: {report['summary']['skipped_system_tables']} 个系统表")
        if md_files_generated > 0 and ddl_files_generated > 0:
            self.logger.info(f"  📁 生成文件: {md_files_generated} 个MD文件，{ddl_files_generated} 个DDL文件")
        elif md_files_generated > 0:
            self.logger.info(f"  📁 生成文件: {md_files_generated} 个MD文件")
        elif ddl_files_generated > 0:
            self.logger.info(f"  📁 生成文件: {ddl_files_generated} 个DDL文件")
        else:
            self.logger.info(f"  📁 生成文件: 0 个")
        self.logger.info(f"  🕐 总耗时: {total_time:.2f} 秒")
        
        if self.failed_tables:
            self.logger.warning(f"❌ 失败的表: {', '.join(self.failed_tables)}")
        
        # 写入文件名映射报告
        self.file_manager.write_mapping_report()
        
        return report
    
    async def check_database_permissions(self) -> Dict[str, bool]:
        """检查数据库权限（供外部调用）"""
        inspector = ToolRegistry.get_tool("database_inspector", db_connection=self.db_connection)
        await inspector._create_connection_pool()
        checker = DatabasePermissionChecker(inspector)
        return await checker.check_permissions()