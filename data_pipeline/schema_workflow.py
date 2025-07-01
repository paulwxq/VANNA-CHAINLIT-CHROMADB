"""
Schema工作流编排器
统一管理完整的数据库Schema处理流程
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from data_pipeline.ddl_generation.training_data_agent import SchemaTrainingDataAgent
from data_pipeline.qa_generation.qs_agent import QuestionSQLGenerationAgent
from data_pipeline.validators.sql_validation_agent import SQLValidationAgent
from data_pipeline.config import SCHEMA_TOOLS_CONFIG
from data_pipeline.dp_logging import get_logger


class SchemaWorkflowOrchestrator:
    """端到端的Schema处理编排器 - 完整工作流程"""
    
    def __init__(self, 
                 db_connection: str,
                 table_list_file: str,
                 business_context: str,
                 output_dir: str = None,
                 task_id: str = None,
                 enable_sql_validation: bool = True,
                 enable_llm_repair: bool = True,
                 modify_original_file: bool = True,
                 enable_training_data_load: bool = True):
        """
        初始化Schema工作流编排器
        
        Args:
            db_connection: 数据库连接字符串 (postgresql://user:pass@host:port/dbname)
            table_list_file: 表清单文件路径
            business_context: 业务上下文描述
            output_dir: 输出目录
            task_id: 任务ID (API模式传递，脚本模式自动生成)
            enable_sql_validation: 是否启用SQL验证
            enable_llm_repair: 是否启用LLM修复功能
            modify_original_file: 是否修改原始JSON文件
            enable_training_data_load: 是否启用训练数据加载
        """
        self.db_connection = db_connection
        self.table_list_file = table_list_file
        self.business_context = business_context
        self.db_name = self._extract_db_name_from_connection(db_connection)
        self.enable_sql_validation = enable_sql_validation
        self.enable_llm_repair = enable_llm_repair
        self.modify_original_file = modify_original_file
        self.enable_training_data_load = enable_training_data_load
        
        # 处理task_id
        if task_id is None:
            # 脚本模式：自动生成manual开头的task_id
            self.task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            # API模式：使用传递的task_id
            self.task_id = task_id
        
        # 设置输出目录
        if output_dir is None:
            # 脚本模式或未指定输出目录时，使用任务目录
            # 获取项目根目录的绝对路径
            project_root = Path(__file__).parent.parent
            self.output_dir = project_root / "data_pipeline" / "training_data" / self.task_id
        else:
            # API模式或明确指定输出目录时，使用指定的目录
            self.output_dir = Path(output_dir)
            
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
            
        # 初始化独立日志系统
        self.logger = get_logger("SchemaWorkflowOrchestrator", self.task_id)
        
        # 工作流程状态
        self.workflow_state = {
            "start_time": None,
            "end_time": None,
            "current_step": None,
            "completed_steps": [],
            "failed_steps": [],
            "artifacts": {},  # 存储各步骤产生的文件
            "statistics": {}
        }
    
    def _extract_db_name_from_connection(self, connection_string: str) -> str:
        """
        从数据库连接字符串中提取数据库名称
        
        Args:
            connection_string: PostgreSQL连接字符串
            
        Returns:
            str: 数据库名称
        """
        try:
            # 处理标准的PostgreSQL连接字符串: postgresql://user:pass@host:port/dbname
            if '/' in connection_string:
                # 取最后一个 '/' 后面的部分作为数据库名
                db_name = connection_string.split('/')[-1]
                # 移除可能的查询参数
                if '?' in db_name:
                    db_name = db_name.split('?')[0]
                return db_name if db_name else "database"
            else:
                return "database"
        except Exception:
            return "database"
    
    async def execute_complete_workflow(self) -> Dict[str, Any]:
        """
        执行完整的Schema处理工作流程
        
        Returns:
            完整的工作流程报告
        """
        self.workflow_state["start_time"] = time.time()
        self.logger.info("🚀 开始执行Schema工作流编排")
        self.logger.info(f"📁 输出目录: {self.output_dir}")
        self.logger.info(f"🏢 业务背景: {self.business_context}")
        self.logger.info(f"💾 数据库: {self.db_name}")
        
        try:
            # 步骤1: 生成DDL和MD文件
            await self._execute_step_1_ddl_md_generation()
            
            # 步骤2: 生成Question-SQL对
            await self._execute_step_2_question_sql_generation()
            
            # 步骤3: 验证和修正SQL（可选）
            if self.enable_sql_validation:
                await self._execute_step_3_sql_validation()
            else:
                self.logger.info("⏭️ 跳过SQL验证步骤")
            
            # 步骤4: 训练数据加载（可选）
            if self.enable_training_data_load:
                await self._execute_step_4_training_data_load()
            else:
                self.logger.info("⏭️ 跳过训练数据加载步骤")
            
            # 设置结束时间
            self.workflow_state["end_time"] = time.time()
            
            # 生成最终报告
            final_report = await self._generate_final_report()
            
            self.logger.info("✅ Schema工作流编排完成")
            
            return final_report
            
        except Exception as e:
            self.workflow_state["end_time"] = time.time()
            self.logger.exception(f"❌ 工作流程执行失败: {str(e)}")
            
            error_report = await self._generate_error_report(e)
            return error_report
    
    async def _execute_step_1_ddl_md_generation(self):
        """步骤1: 生成DDL和MD文件"""
        self.workflow_state["current_step"] = "ddl_md_generation"
        self.logger.info("=" * 60)
        self.logger.info("📝 步骤1: 开始生成DDL和MD文件")
        self.logger.info("=" * 60)
        
        step_start_time = time.time()
        
        try:
            # 创建DDL/MD生成Agent
            ddl_md_agent = SchemaTrainingDataAgent(
                db_connection=self.db_connection,
                table_list_file=self.table_list_file,
                business_context=self.business_context,
                output_dir=str(self.output_dir),
                task_id=self.task_id,  # 传递task_id
                pipeline="full"
            )
            
            # 执行DDL/MD生成
            ddl_md_result = await ddl_md_agent.generate_training_data()
            
            step_duration = time.time() - step_start_time
            
            # 记录结果
            self.workflow_state["completed_steps"].append("ddl_md_generation")
            self.workflow_state["artifacts"]["ddl_md_generation"] = {
                "total_tables": ddl_md_result.get("summary", {}).get("total_tables", 0),
                "processed_successfully": ddl_md_result.get("summary", {}).get("processed_successfully", 0),
                "failed": ddl_md_result.get("summary", {}).get("failed", 0),
                "files_generated": ddl_md_result.get("statistics", {}).get("files_generated", 0),
                "duration": step_duration
            }
            self.workflow_state["statistics"]["step1_duration"] = step_duration
            
            processed_tables = ddl_md_result.get("summary", {}).get("processed_successfully", 0)
            self.logger.info(f"✅ 步骤1完成: 成功处理 {processed_tables} 个表，耗时 {step_duration:.2f}秒")
            
        except Exception as e:
            self.workflow_state["failed_steps"].append("ddl_md_generation")
            self.logger.error(f"❌ 步骤1失败: {str(e)}")
            raise
    
    async def _execute_step_2_question_sql_generation(self):
        """步骤2: 生成Question-SQL对"""
        self.workflow_state["current_step"] = "question_sql_generation"
        self.logger.info("=" * 60)
        self.logger.info("🤖 步骤2: 开始生成Question-SQL对")
        self.logger.info("=" * 60)
        
        step_start_time = time.time()
        
        try:
            # 创建Question-SQL生成Agent
            qs_agent = QuestionSQLGenerationAgent(
                output_dir=str(self.output_dir),
                table_list_file=self.table_list_file,
                business_context=self.business_context,
                db_name=self.db_name,
                task_id=self.task_id  # 传递task_id
            )
            
            # 执行Question-SQL生成
            qs_result = await qs_agent.generate()
            
            step_duration = time.time() - step_start_time
            
            # 记录结果
            self.workflow_state["completed_steps"].append("question_sql_generation")
            self.workflow_state["artifacts"]["question_sql_generation"] = {
                "output_file": str(qs_result.get("output_file", "")),
                "total_questions": qs_result.get("total_questions", 0),
                "total_themes": qs_result.get("total_themes", 0),
                "successful_themes": qs_result.get("successful_themes", 0),
                "failed_themes": qs_result.get("failed_themes", []),
                "duration": step_duration
            }
            self.workflow_state["statistics"]["step2_duration"] = step_duration
            
            total_questions = qs_result.get("total_questions", 0)
            self.logger.info(f"✅ 步骤2完成: 生成了 {total_questions} 个问答对，耗时 {step_duration:.2f}秒")
            
        except Exception as e:
            self.workflow_state["failed_steps"].append("question_sql_generation")
            self.logger.error(f"❌ 步骤2失败: {str(e)}")
            raise
    
    async def _execute_step_3_sql_validation(self):
        """步骤3: 验证和修正SQL"""
        self.workflow_state["current_step"] = "sql_validation"
        self.logger.info("=" * 60)
        self.logger.info("🔍 步骤3: 开始验证和修正SQL")
        self.logger.info("=" * 60)
        
        step_start_time = time.time()
        
        try:
            # 获取步骤2生成的文件
            qs_artifacts = self.workflow_state["artifacts"].get("question_sql_generation", {})
            qs_file = qs_artifacts.get("output_file")
            
            if not qs_file or not Path(qs_file).exists():
                raise FileNotFoundError(f"找不到Question-SQL文件: {qs_file}")
            
            self.logger.info(f"📄 验证文件: {qs_file}")
            
            # 创建SQL验证Agent，通过参数传递配置而非修改全局配置
            sql_validator = SQLValidationAgent(
                db_connection=self.db_connection,
                input_file=str(qs_file),
                output_dir=str(self.output_dir),
                task_id=self.task_id,  # 传递task_id
                enable_sql_repair=self.enable_llm_repair,
                modify_original_file=self.modify_original_file
            )
            
            # 执行SQL验证和修正
            validation_result = await sql_validator.validate()
            
            step_duration = time.time() - step_start_time
            
            # 记录结果
            self.workflow_state["completed_steps"].append("sql_validation")
            
            summary = validation_result.get("summary", {})
            self.workflow_state["artifacts"]["sql_validation"] = {
                "original_sql_count": summary.get("total_questions", 0),
                "valid_sql_count": summary.get("valid_sqls", 0),
                "invalid_sql_count": summary.get("invalid_sqls", 0),
                "success_rate": summary.get("success_rate", 0),
                "repair_stats": summary.get("repair_stats", {}),
                "file_modification_stats": summary.get("file_modification_stats", {}),
                "average_execution_time": summary.get("average_execution_time", 0),
                "total_retries": summary.get("total_retries", 0),
                "duration": step_duration
            }
            self.workflow_state["statistics"]["step3_duration"] = step_duration
            
            success_rate = summary.get("success_rate", 0)
            valid_count = summary.get("valid_sqls", 0)
            total_count = summary.get("total_questions", 0)
            
            self.logger.info(f"✅ 步骤3完成: SQL验证成功率 {success_rate:.1%} ({valid_count}/{total_count})，耗时 {step_duration:.2f}秒")
            
            # 显示修复统计
            repair_stats = summary.get("repair_stats", {})
            if repair_stats.get("attempted", 0) > 0:
                self.logger.info(f"🔧 修复统计: 尝试 {repair_stats['attempted']}，成功 {repair_stats['successful']}，失败 {repair_stats['failed']}")
            
            # 显示文件修改统计
            file_stats = summary.get("file_modification_stats", {})
            if file_stats.get("modified", 0) > 0 or file_stats.get("deleted", 0) > 0:
                self.logger.info(f"📝 文件修改: 更新 {file_stats.get('modified', 0)} 个SQL，删除 {file_stats.get('deleted', 0)} 个无效项")
            
        except Exception as e:
            self.workflow_state["failed_steps"].append("sql_validation")
            self.logger.error(f"❌ 步骤3失败: {str(e)}")
            raise
    
    async def _execute_step_4_training_data_load(self):
        """步骤4: 训练数据加载"""
        self.workflow_state["current_step"] = "training_data_load"
        self.logger.info("=" * 60)
        self.logger.info("🎯 步骤4: 开始加载训练数据")
        self.logger.info("=" * 60)
        
        step_start_time = time.time()
        
        try:
            # 确保输出目录存在所需的训练数据
            training_data_dir = str(self.output_dir)
            self.logger.info(f"📁 训练数据目录: {training_data_dir}")
            
            # 导入训练器模块
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            from data_pipeline.trainer.run_training import process_training_files
            
            # 执行训练数据加载
            self.logger.info("🔄 开始处理训练文件...")
            load_successful = process_training_files(training_data_dir, self.task_id)
            
            step_duration = time.time() - step_start_time
            
            if load_successful:
                # 获取统计信息
                from data_pipeline.trainer.vanna_trainer import flush_training, shutdown_trainer
                
                # 刷新批处理器
                self.logger.info("🔄 刷新批处理器...")
                flush_training()
                shutdown_trainer()
                
                # 验证加载结果
                try:
                    from core.vanna_llm_factory import create_vanna_instance
                    vn = create_vanna_instance()
                    training_data = vn.get_training_data()
                    
                    if training_data is not None and not training_data.empty:
                        total_records = len(training_data)
                        self.logger.info(f"✅ 成功加载 {total_records} 条训练数据")
                        
                        # 统计数据类型
                        if 'training_data_type' in training_data.columns:
                            type_counts = training_data['training_data_type'].value_counts().to_dict()
                        else:
                            type_counts = {}
                    else:
                        total_records = 0
                        type_counts = {}
                        self.logger.warning("⚠️ 未能验证训练数据加载结果")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ 验证训练数据时出错: {e}")
                    total_records = 0
                    type_counts = {}
                
                # 记录结果
                self.workflow_state["completed_steps"].append("training_data_load")
                self.workflow_state["artifacts"]["training_data_load"] = {
                    "training_data_dir": training_data_dir,
                    "load_successful": True,
                    "total_records": total_records,
                    "data_type_counts": type_counts,
                    "duration": step_duration
                }
                self.workflow_state["statistics"]["step4_duration"] = step_duration
                
                self.logger.info(f"✅ 步骤4完成: 成功加载训练数据，耗时 {step_duration:.2f}秒")
                
            else:
                raise Exception("训练数据加载失败：未找到可处理的训练文件")
                
        except Exception as e:
            self.workflow_state["failed_steps"].append("training_data_load")
            self.logger.error(f"❌ 步骤4失败: {str(e)}")
            raise
    
    async def _generate_final_report(self) -> Dict[str, Any]:
        """生成最终工作流程报告"""
        total_duration = self.workflow_state["end_time"] - self.workflow_state["start_time"]
        
        # 计算最终输出文件
        qs_artifacts = self.workflow_state["artifacts"].get("question_sql_generation", {})
        final_output_file = qs_artifacts.get("output_file", "")
        
        # 计算最终问题数量
        if "sql_validation" in self.workflow_state["artifacts"]:
            # 如果有验证步骤，使用验证后的数量
            validation_artifacts = self.workflow_state["artifacts"]["sql_validation"]
            final_question_count = validation_artifacts.get("valid_sql_count", 0)
        else:
            # 否则使用生成的数量
            final_question_count = qs_artifacts.get("total_questions", 0)
        
        report = {
            "success": True,
            "workflow_summary": {
                "total_duration": round(total_duration, 2),
                "completed_steps": self.workflow_state["completed_steps"],
                "failed_steps": self.workflow_state["failed_steps"],
                "total_steps": len(self.workflow_state["completed_steps"]),
                "workflow_started": datetime.fromtimestamp(self.workflow_state["start_time"]).isoformat(),
                "workflow_completed": datetime.fromtimestamp(self.workflow_state["end_time"]).isoformat()
            },
            "input_parameters": {
                "db_connection": self._mask_connection_string(self.db_connection),
                "table_list_file": self.table_list_file,
                "business_context": self.business_context,
                "db_name": self.db_name,
                "output_directory": str(self.output_dir),
                "enable_sql_validation": self.enable_sql_validation,
                "enable_llm_repair": self.enable_llm_repair,
                "modify_original_file": self.modify_original_file,
                "enable_training_data_load": self.enable_training_data_load
            },
            "processing_results": {
                "ddl_md_generation": self.workflow_state["artifacts"].get("ddl_md_generation", {}),
                "question_sql_generation": self.workflow_state["artifacts"].get("question_sql_generation", {}),
                "sql_validation": self.workflow_state["artifacts"].get("sql_validation", {}),
                "training_data_load": self.workflow_state["artifacts"].get("training_data_load", {})
            },
            "final_outputs": {
                "primary_output_file": final_output_file,
                "output_directory": str(self.output_dir),
                "final_question_count": final_question_count,
                "backup_files_created": self.modify_original_file
            },
            "performance_metrics": {
                "step1_duration": round(self.workflow_state["statistics"].get("step1_duration", 0), 2),
                "step2_duration": round(self.workflow_state["statistics"].get("step2_duration", 0), 2),
                "step3_duration": round(self.workflow_state["statistics"].get("step3_duration", 0), 2),
                "step4_duration": round(self.workflow_state["statistics"].get("step4_duration", 0), 2),
                "total_duration": round(total_duration, 2)
            }
        }
        
        return report
    
    async def _generate_error_report(self, error: Exception) -> Dict[str, Any]:
        """生成错误报告"""
        total_duration = self.workflow_state["end_time"] - self.workflow_state["start_time"]
        
        return {
            "success": False,
            "error": {
                "message": str(error),
                "type": type(error).__name__,
                "failed_step": self.workflow_state["current_step"]
            },
            "workflow_summary": {
                "total_duration": round(total_duration, 2),
                "completed_steps": self.workflow_state["completed_steps"],
                "failed_steps": self.workflow_state["failed_steps"],
                "workflow_started": datetime.fromtimestamp(self.workflow_state["start_time"]).isoformat() if self.workflow_state["start_time"] else None,
                "workflow_failed": datetime.fromtimestamp(self.workflow_state["end_time"]).isoformat() if self.workflow_state["end_time"] else None
            },
            "partial_results": self.workflow_state["artifacts"],
            "input_parameters": {
                "db_connection": self._mask_connection_string(self.db_connection),
                "table_list_file": self.table_list_file,
                "business_context": self.business_context,
                "db_name": self.db_name,
                "output_directory": str(self.output_dir)
            }
        }
    
    def _mask_connection_string(self, conn_str: str) -> str:
        """隐藏连接字符串中的敏感信息"""
        import re
        return re.sub(r':[^:@]+@', ':***@', conn_str)
    
    def print_final_summary(self, report: Dict[str, Any]):
        """打印最终摘要"""
        self.logger.info("=" * 80)
        self.logger.info("📊 工作流程执行摘要")
        self.logger.info("=" * 80)
        
        if report["success"]:
            summary = report["workflow_summary"]
            results = report["processing_results"]
            outputs = report["final_outputs"]
            metrics = report["performance_metrics"]
            
            self.logger.info(f"✅ 工作流程执行成功")
            self.logger.info(f"⏱️  总耗时: {summary['total_duration']} 秒")
            self.logger.info(f"📝 完成步骤: {len(summary['completed_steps'])}/{summary['total_steps']}")
            
            # DDL/MD生成结果
            if "ddl_md_generation" in results:
                ddl_md = results["ddl_md_generation"]
                self.logger.info(f"📋 DDL/MD生成: {ddl_md.get('processed_successfully', 0)} 个表成功处理")
            
            # Question-SQL生成结果
            if "question_sql_generation" in results:
                qs = results["question_sql_generation"]
                self.logger.info(f"🤖 Question-SQL生成: {qs.get('total_questions', 0)} 个问答对")
            
            # SQL验证结果
            if "sql_validation" in results:
                validation = results["sql_validation"]
                success_rate = validation.get('success_rate', 0)
                self.logger.info(f"🔍 SQL验证: {success_rate:.1%} 成功率 ({validation.get('valid_sql_count', 0)}/{validation.get('original_sql_count', 0)})")
            
            self.logger.info(f"📁 输出目录: {outputs['output_directory']}")
            self.logger.info(f"📄 主要输出文件: {outputs['primary_output_file']}")
            self.logger.info(f"❓ 最终问题数量: {outputs['final_question_count']}")
            
        else:
            error = report["error"]
            summary = report["workflow_summary"]
            
            self.logger.error(f"❌ 工作流程执行失败")
            self.logger.error(f"💥 失败原因: {error['message']}")
            self.logger.error(f"💥 失败步骤: {error['failed_step']}")
            self.logger.error(f"⏱️  执行耗时: {summary['total_duration']} 秒")
            self.logger.error(f"✅ 已完成步骤: {', '.join(summary['completed_steps']) if summary['completed_steps'] else '无'}")
        
        self.logger.info("=" * 80)


# 便捷的命令行接口
def setup_argument_parser():
    """设置命令行参数解析器"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Schema工作流编排器 - 端到端的Schema处理流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 完整工作流程
  python -m data_pipeline.schema_workflow \\
    --db-connection "postgresql://user:pass@localhost:5432/highway_db" \\
    --table-list tables.txt \\
    --business-context "高速公路服务区管理系统" \\
    --output-dir ./data_pipeline/training_data/
  
  # 跳过SQL验证
  python -m data_pipeline.schema_workflow \\
    --db-connection "postgresql://user:pass@localhost:5432/ecommerce_db" \\
    --table-list tables.txt \\
    --business-context "电商系统" \\
    --skip-validation
  
  # 禁用LLM修复
  python -m data_pipeline.schema_workflow \\
    --db-connection "postgresql://user:pass@localhost:5432/management_db" \\
    --table-list tables.txt \\
    --business-context "管理系统" \\
    --disable-llm-repair
  
  # 跳过训练数据加载
  python -m data_pipeline.schema_workflow \\
    --db-connection "postgresql://user:pass@localhost:5432/management_db" \\
    --table-list tables.txt \\
    --business-context "管理系统" \\
    --skip-training-load
        """
    )
    
    # 必需参数
    parser.add_argument(
        "--db-connection",
        required=True,
        help="数据库连接字符串 (postgresql://user:pass@host:port/dbname)"
    )
    
    parser.add_argument(
        "--table-list",
        required=True,
        help="表清单文件路径"
    )
    
    parser.add_argument(
        "--business-context",
        required=True,
        help="业务上下文描述"
    )
    
    
    # 可选参数
    parser.add_argument(
        "--output-dir",
        default="./data_pipeline/training_data/",
        help="输出目录（默认：./data_pipeline/training_data/）"
    )
    
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="跳过SQL验证步骤"
    )
    
    parser.add_argument(
        "--disable-llm-repair",
        action="store_true",
        help="禁用LLM修复功能"
    )
    
    parser.add_argument(
        "--no-modify-file",
        action="store_true",
        help="不修改原始JSON文件（仅生成报告）"
    )
    
    parser.add_argument(
        "--skip-training-load",
        action="store_true",
        help="跳过训练数据加载步骤"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用详细日志输出"
    )
    
    parser.add_argument(
        "--log-file",
        help="日志文件路径"
    )
    
    return parser


async def main():
    """命令行入口点"""
    import sys
    import os
    
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 验证输入文件
    if not os.path.exists(args.table_list):
        # 为脚本模式生成task_id
        from datetime import datetime
        script_task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # 使用独立日志系统
        from data_pipeline.dp_logging import get_logger
        logger = get_logger("SchemaWorkflow", script_task_id)
        logger.error(f"错误: 表清单文件不存在: {args.table_list}")
        sys.exit(1)
    
    try:
        # 创建并执行工作流编排器
        orchestrator = SchemaWorkflowOrchestrator(
            db_connection=args.db_connection,
            table_list_file=args.table_list,
            business_context=args.business_context,
            output_dir=args.output_dir,
            enable_sql_validation=not args.skip_validation,
            enable_llm_repair=not args.disable_llm_repair,
            modify_original_file=not args.no_modify_file,
            enable_training_data_load=not args.skip_training_load
        )
        
        # 获取logger用于启动信息
        # 为脚本模式生成task_id
        from datetime import datetime
        script_task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # 使用独立日志系统
        from data_pipeline.dp_logging import get_logger
        logger = get_logger("SchemaWorkflow", script_task_id)
        logger.info(f"🚀 开始执行Schema工作流编排...")
        logger.info(f"📁 输出目录: {args.output_dir}")
        logger.info(f"📋 表清单: {args.table_list}")
        logger.info(f"🏢 业务背景: {args.business_context}")
        logger.info(f"💾 数据库: {orchestrator.db_name}")
        logger.info(f"🔍 SQL验证: {'启用' if not args.skip_validation else '禁用'}")
        logger.info(f"🔧 LLM修复: {'启用' if not args.disable_llm_repair else '禁用'}")
        logger.info(f"🎯 训练数据加载: {'启用' if not args.skip_training_load else '禁用'}")
        
        # 执行完整工作流程
        report = await orchestrator.execute_complete_workflow()
        
        # 打印详细摘要
        orchestrator.print_final_summary(report)
        
        # 输出结果并设置退出码
        if report["success"]:
            if report["processing_results"].get("sql_validation", {}).get("success_rate", 1.0) >= 0.8:
                logger.info(f"\n🎉 工作流程执行成功!")
                exit_code = 0  # 完全成功
            else:
                logger.warning(f"\n⚠️  工作流程执行完成，但SQL验证成功率较低")
                exit_code = 1  # 部分成功
        else:
            logger.error(f"\n❌ 工作流程执行失败")
            exit_code = 2  # 失败
        
        logger.info(f"📄 主要输出文件: {report['final_outputs']['primary_output_file']}")
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("\n\n⏹️  用户中断，程序退出")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ 程序执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 