"""
Data Pipeline API 简化任务工作流

集成简化后的数据库管理器和文件管理器，提供任务执行功能
"""

import asyncio
import json
import os
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

from data_pipeline.schema_workflow import SchemaWorkflowOrchestrator
from data_pipeline.api.simple_db_manager import SimpleTaskManager
from data_pipeline.api.simple_file_manager import SimpleFileManager
from data_pipeline.dp_logging import get_logger


class SimpleWorkflowExecutor:
    """简化的任务工作流执行器"""
    
    def __init__(self, task_id: str, backup_vector_tables: bool = False, truncate_vector_tables: bool = False, skip_training: bool = False):
        """
        初始化工作流执行器
        
        Args:
            task_id: 任务ID
            backup_vector_tables: 是否备份vector表数据
            truncate_vector_tables: 是否清空vector表数据（自动启用备份）
            skip_training: 是否跳过训练文件处理，仅执行Vector表管理
        """
        self.task_id = task_id
        self.backup_vector_tables = backup_vector_tables
        self.truncate_vector_tables = truncate_vector_tables
        self.skip_training = skip_training
        
        # 参数逻辑：truncate自动启用backup
        if self.truncate_vector_tables:
            self.backup_vector_tables = True
        
        self.logger = get_logger("SimpleWorkflowExecutor", task_id)
        
        # 记录Vector表管理参数状态
        if self.backup_vector_tables or self.truncate_vector_tables:
            self.logger.info(f"🗂️ Vector表管理已启用: backup={self.backup_vector_tables}, truncate={self.truncate_vector_tables}")
        
        # 初始化管理器
        self.task_manager = SimpleTaskManager()
        self.file_manager = SimpleFileManager()
        
        # 任务目录日志记录器
        self.task_dir_logger = None
        
        # 加载任务信息
        self.task_info = None
        self.task_params = None
        self._load_task_info()
    
    def _load_task_info(self):
        """加载任务信息"""
        try:
            self.task_info = self.task_manager.get_task(self.task_id)
            if self.task_info:
                self.task_params = self.task_info.get('parameters', {})
            else:
                raise ValueError(f"任务不存在: {self.task_id}")
        except Exception as e:
            self.logger.error(f"加载任务信息失败: {e}")
            raise
    
    def _ensure_task_directory(self) -> bool:
        """确保任务目录存在"""
        try:
            success = self.file_manager.create_task_directory(self.task_id)
            if success:
                # 写入任务配置文件
                self._write_task_config()
                # 初始化任务目录日志记录器
                self._setup_task_directory_logger()
            return success
        except Exception as e:
            self.logger.error(f"创建任务目录失败: {e}")
            return False
    
    def _write_task_config(self):
        """写入任务配置文件"""
        try:
            task_dir = self.file_manager.get_task_directory(self.task_id)
            config_file = task_dir / "task_config.json"
            
            config_data = {
                "task_id": self.task_id,
                "created_at": self.task_info.get('created_at').isoformat() if self.task_info.get('created_at') else None,
                "parameters": self.task_params,
                "output_directory": str(task_dir)
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"写入任务配置失败: {e}")
    
    def _setup_task_directory_logger(self):
        """设置任务目录日志记录器"""
        try:
            task_dir = self.file_manager.get_task_directory(self.task_id)
            log_file = task_dir / "data_pipeline.log"
            
            # 创建专门的任务目录日志记录器
            self.task_dir_logger = logging.getLogger(f"TaskDir_{self.task_id}")
            self.task_dir_logger.setLevel(logging.DEBUG)
            
            # 清除已有处理器
            self.task_dir_logger.handlers.clear()
            self.task_dir_logger.propagate = False
            
            # 创建文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # 设置详细的日志格式
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            self.task_dir_logger.addHandler(file_handler)
            
            # 记录初始化信息
            self.task_dir_logger.info(f"任务目录日志初始化完成 - 任务ID: {self.task_id}")
            self.task_dir_logger.info(f"任务参数: {json.dumps(self.task_params, ensure_ascii=False, default=str)}")
            
        except Exception as e:
            self.logger.error(f"设置任务目录日志记录器失败: {e}")
    
    def _log_to_task_directory(self, level: str, message: str, step_name: str = None):
        """记录日志到任务目录"""
        if self.task_dir_logger:
            try:
                if step_name:
                    message = f"[{step_name}] {message}"
                
                log_level = getattr(logging, level.upper(), logging.INFO)
                self.task_dir_logger.log(log_level, message)
            except Exception as e:
                self.logger.error(f"记录任务目录日志失败: {e}")
    
    def _backup_existing_files_if_needed(self):
        """如果需要，备份现有文件（仅备份文件，不包括子目录）"""
        try:
            task_dir = self.file_manager.get_task_directory(self.task_id)
            
            # 严格检查：只允许保留指定文件
            allowed_files = {"table_list.txt", "data_pipeline.log"}
            
            # 扫描任务目录中的文件（排除子目录和允许的文件）
            files_to_backup = []
            for item in task_dir.iterdir():
                if item.is_file() and item.name not in allowed_files:
                    files_to_backup.append(item)
            
            # 如果没有文件需要备份，直接返回
            if not files_to_backup:
                self._log_to_task_directory("INFO", "任务目录中没有需要备份的文件")
                return
            
            # 创建备份目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir_name = f"file_bak_{timestamp}"
            backup_dir = task_dir / backup_dir_name
            
            # 处理备份目录名冲突
            counter = 1
            while backup_dir.exists():
                backup_dir = task_dir / f"{backup_dir_name}_{counter}"
                counter += 1
            
            backup_dir.mkdir(parents=True)
            
            # 移动文件到备份目录
            moved_files = []
            failed_files = []
            
            for file_path in files_to_backup:
                try:
                    target_path = backup_dir / file_path.name
                    shutil.move(str(file_path), str(target_path))
                    moved_files.append(file_path.name)
                    self._log_to_task_directory("DEBUG", f"文件已备份: {file_path.name}")
                except Exception as e:
                    failed_files.append({"file": file_path.name, "error": str(e)})
                    self._log_to_task_directory("WARNING", f"文件备份失败: {file_path.name} - {e}")
            
            # 生成备份记录文件
            backup_info = {
                "backup_time": datetime.now().isoformat(),
                "backup_directory": backup_dir.name,
                "moved_files": moved_files,
                "failed_files": failed_files,
                "task_id": self.task_id
            }
            
            backup_info_file = backup_dir / "backup_info.json"
            with open(backup_info_file, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, ensure_ascii=False, indent=2)
            
            # 记录备份完成
            self._log_to_task_directory("INFO", 
                f"文件备份完成: {len(moved_files)} 个文件已移动到 {backup_dir.name}")
            
            # 如果有文件备份失败，中断作业
            if failed_files:
                error_msg = f"❌ 无法清理工作目录，以下文件移动失败: {[f['file'] for f in failed_files]}"
                self._log_to_task_directory("ERROR", error_msg)
                raise Exception(error_msg)
        
        except Exception as e:
            # 备份失败必须中断作业
            error_msg = f"❌ 文件备份过程失败，作业中断: {e}"
            self._log_to_task_directory("ERROR", error_msg)
            raise Exception(error_msg)
    
    def _resolve_table_list_file_path(self) -> str:
        """解析表清单文件路径"""
        table_list_file = self.task_params['table_list_file']
        
        # 检查是否使用文件上传模式
        if self.task_params.get('file_upload_mode', False) or '{task_directory}' in table_list_file:
            # 文件上传模式：检查任务目录中的文件
            task_dir = self.file_manager.get_task_directory(self.task_id)
            
            # 替换占位符
            if '{task_directory}' in table_list_file:
                resolved_path = table_list_file.replace('{task_directory}', str(task_dir))
            else:
                from data_pipeline.config import SCHEMA_TOOLS_CONFIG
                upload_config = SCHEMA_TOOLS_CONFIG.get("file_upload", {})
                target_filename = upload_config.get("target_filename", "table_list.txt")
                resolved_path = str(task_dir / target_filename)
            
            # 检查文件是否存在
            if not Path(resolved_path).exists():
                raise FileNotFoundError(
                    f"表清单文件不存在: {resolved_path}。"
                    f"请先上传表清单文件到任务 {self.task_id}，然后再执行工作流。"
                )
            
            return resolved_path
        else:
            # 传统模式：使用指定的文件路径
            if not Path(table_list_file).exists():
                raise FileNotFoundError(f"表清单文件不存在: {table_list_file}")
            return table_list_file
    
    def _create_orchestrator(self) -> SchemaWorkflowOrchestrator:
        """创建工作流编排器"""
        task_dir = self.file_manager.get_task_directory(self.task_id)
        
        # 解析表清单文件路径
        table_list_file = self._resolve_table_list_file_path()
        
        return SchemaWorkflowOrchestrator(
            db_connection=self.task_params['db_connection'],
            table_list_file=table_list_file,
            business_context=self.task_params['business_context'],
            output_dir=str(task_dir),
            task_id=self.task_id,  # 传递task_id给编排器
            enable_sql_validation=self.task_params.get('enable_sql_validation', True),
            enable_llm_repair=self.task_params.get('enable_llm_repair', True),
            modify_original_file=self.task_params.get('modify_original_file', True),
            enable_training_data_load=self.task_params.get('enable_training_data_load', True),
            # 新增：Vector表管理参数
            backup_vector_tables=self.backup_vector_tables,
            truncate_vector_tables=self.truncate_vector_tables,
            skip_training=self.skip_training
        )
    
    @contextmanager
    def _step_execution(self, step_name: str):
        """步骤执行上下文管理器"""
        execution_id = None
        
        try:
            # 开始执行
            execution_id = self.task_manager.start_step(self.task_id, step_name)
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", f"开始执行步骤: {step_name}", step_name)
            
            yield execution_id
            
            # 成功完成
            self.task_manager.complete_step(self.task_id, step_name, 'completed')
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", f"步骤执行完成: {step_name}", step_name)
            
        except Exception as e:
            # 执行失败
            error_msg = str(e)
            
            self.task_manager.complete_step(self.task_id, step_name, 'failed', error_msg)
            
            # 记录到任务目录日志
            self._log_to_task_directory("ERROR", f"步骤执行失败: {step_name} - {error_msg}", step_name)
            raise
    
    async def execute_complete_workflow(self) -> Dict[str, Any]:
        """执行完整工作流"""
        try:
            # 🆕 新增：先备份现有文件（清理环境）
            self._backup_existing_files_if_needed()
            
            # 确保任务目录存在并写入新配置
            if not self._ensure_task_directory():
                raise Exception("无法创建任务目录")
            
            # 开始任务
            self.task_manager.update_task_status(self.task_id, 'in_progress')
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", "完整工作流任务开始执行")
            
            # 创建工作流编排器
            orchestrator = self._create_orchestrator()
            
            # 重定向SchemaWorkflowOrchestrator的日志到任务目录
            self._redirect_orchestrator_logs(orchestrator)
            
            # 分别执行各个步骤，每个步骤都用_step_execution包装
            try:
                # 步骤1: DDL/MD生成
                with self._step_execution("ddl_generation") as execution_id:
                    self._log_to_task_directory("INFO", "开始执行DDL/MD生成步骤", "ddl_generation")
                    await orchestrator._execute_step_1_ddl_md_generation()
                    self._log_to_task_directory("INFO", "DDL/MD生成步骤完成", "ddl_generation")
                
                # 步骤2: Question-SQL生成  
                with self._step_execution("qa_generation") as execution_id:
                    self._log_to_task_directory("INFO", "开始执行Question-SQL生成步骤", "qa_generation")
                    await orchestrator._execute_step_2_question_sql_generation()
                    self._log_to_task_directory("INFO", "Question-SQL生成步骤完成", "qa_generation")
                
                # 步骤3: SQL验证（如果启用）
                if orchestrator.enable_sql_validation:
                    with self._step_execution("sql_validation") as execution_id:
                        self._log_to_task_directory("INFO", "开始执行SQL验证步骤", "sql_validation")
                        await orchestrator._execute_step_3_sql_validation()
                        self._log_to_task_directory("INFO", "SQL验证步骤完成", "sql_validation")
                else:
                    self._log_to_task_directory("INFO", "跳过SQL验证步骤（未启用）", "sql_validation")
                
                # 步骤4: 训练数据加载（如果启用）
                if orchestrator.enable_training_data_load:
                    with self._step_execution("training_load") as execution_id:
                        self._log_to_task_directory("INFO", "开始执行训练数据加载步骤", "training_load")
                        await orchestrator._execute_step_4_training_data_load()
                        self._log_to_task_directory("INFO", "训练数据加载步骤完成", "training_load")
                else:
                    self._log_to_task_directory("INFO", "跳过训练数据加载步骤（未启用）", "training_load")
                
                # 获取工作流结果
                result = {
                    "success": True,
                    "workflow_state": orchestrator.workflow_state,
                    "artifacts": orchestrator.workflow_state.get("artifacts", {})
                }
                
                # 写入结果文件
                self._write_result_file(result)
                
            except Exception as step_error:
                self.logger.error(f"工作流步骤执行失败: {step_error}")
                # 记录到任务目录日志
                self._log_to_task_directory("ERROR", f"工作流步骤执行失败: {step_error}")
                raise
            
            # 完成任务
            self.task_manager.update_task_status(self.task_id, 'completed')
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", "完整工作流任务执行完成")
            
            return {
                "success": True,
                "task_id": self.task_id,
                "execution_mode": "complete",
                "result": result
            }
            
        except Exception as e:
            # 记录错误
            error_msg = str(e)
            self.task_manager.update_task_status(self.task_id, 'failed', error_msg)
            
            # 记录到任务目录日志
            self._log_to_task_directory("ERROR", f"完整工作流任务执行失败: {error_msg}")
            
            return {
                "success": False,
                "task_id": self.task_id,
                "execution_mode": "complete",
                "error": error_msg
            }
    
    async def execute_single_step(self, step_name: str) -> Dict[str, Any]:
        """执行单个步骤"""
        try:
            # 新增：非training_load步骤的Vector表管理参数警告
            if step_name != 'training_load' and (self.backup_vector_tables or self.truncate_vector_tables or self.skip_training):
                self.logger.warning(
                    f"⚠️ Vector表管理参数仅在training_load步骤有效，当前步骤: {step_name}，忽略参数"
                )
                # 临时禁用Vector表管理参数
                temp_backup = self.backup_vector_tables
                temp_truncate = self.truncate_vector_tables
                temp_skip = self.skip_training
                self.backup_vector_tables = False
                self.truncate_vector_tables = False
                self.skip_training = False
            
            # 确保任务目录存在
            if not self._ensure_task_directory():
                raise Exception("无法创建任务目录")
            
            # 更新任务状态
            self.task_manager.update_task_status(self.task_id, 'in_progress')
            
            # 创建工作流编排器（会根据当前参数状态创建）
            orchestrator = self._create_orchestrator()
            
            # 重定向SchemaWorkflowOrchestrator的日志到任务目录
            self._redirect_orchestrator_logs(orchestrator)
            
            # 执行指定步骤
            result = None
            with self._step_execution(step_name) as execution_id:
                if step_name == "ddl_generation":
                    await orchestrator._execute_step_1_ddl_md_generation()
                    result = orchestrator.workflow_state["artifacts"].get("ddl_md_generation", {})
                    
                elif step_name == "qa_generation":
                    await orchestrator._execute_step_2_question_sql_generation()
                    result = orchestrator.workflow_state["artifacts"].get("question_sql_generation", {})
                    
                elif step_name == "sql_validation":
                    await orchestrator._execute_step_3_sql_validation()
                    result = orchestrator.workflow_state["artifacts"].get("sql_validation", {})
                    
                elif step_name == "training_load":
                    await orchestrator._execute_step_4_training_data_load()
                    result = orchestrator.workflow_state["artifacts"].get("training_data_load", {})
                    
                else:
                    raise ValueError(f"不支持的步骤: {step_name}")
                
                # 写入步骤结果文件
                self._write_step_result_file(step_name, result)
            
            # 恢复原始参数状态（如果被临时修改）
            if step_name != 'training_load' and 'temp_backup' in locals():
                self.backup_vector_tables = temp_backup
                self.truncate_vector_tables = temp_truncate
                self.skip_training = temp_skip
            
            # 检查是否所有步骤都已完成
            self._update_overall_task_status()
            
            return {
                "success": True,
                "task_id": self.task_id,
                "execution_mode": "step",
                "step_name": step_name,
                "result": result
            }
            
        except Exception as e:
            # 记录错误
            error_msg = str(e)
            self.task_manager.update_task_status(self.task_id, 'failed', error_msg)
            
            # 记录到任务目录日志
            self._log_to_task_directory("ERROR", f"步骤执行失败: {step_name} - {error_msg}", step_name)
            
            return {
                "success": False,
                "task_id": self.task_id,
                "execution_mode": "step",
                "step_name": step_name,
                "error": error_msg
            }
    
    def _write_result_file(self, result: Dict[str, Any]):
        """写入完整结果文件"""
        try:
            task_dir = self.file_manager.get_task_directory(self.task_id)
            result_file = task_dir / "task_result.json"
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"写入结果文件失败: {e}")
    
    def _write_step_result_file(self, step_name: str, result: Dict[str, Any]):
        """写入步骤结果文件"""
        try:
            task_dir = self.file_manager.get_task_directory(self.task_id)
            result_file = task_dir / f"{step_name}_result.json"
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"写入步骤结果文件失败: {e}")
    
    def _update_overall_task_status(self):
        """更新整体任务状态"""
        try:
            # 检查所有步骤的完成情况
            steps = self.task_manager.get_task_steps(self.task_id)
            
            completed_steps = set()
            failed_steps = set()
            
            for step in steps:
                if step['step_status'] == 'completed':
                    completed_steps.add(step['step_name'])
                elif step['step_status'] == 'failed':
                    failed_steps.add(step['step_name'])
            
            # 检查是否有失败的步骤
            if failed_steps:
                self.task_manager.update_task_status(self.task_id, 'failed')
                return
            
            # 检查是否完成了必要步骤
            required_steps = {"ddl_generation", "qa_generation"}
            if required_steps.issubset(completed_steps):
                # 检查是否有可选步骤完成
                optional_steps = {"sql_validation", "training_load"}
                if completed_steps.intersection(optional_steps):
                    if len(completed_steps) >= 3:
                        self.task_manager.update_task_status(self.task_id, 'completed')
                    else:
                        self.task_manager.update_task_status(self.task_id, 'partial_completed')
                else:
                    self.task_manager.update_task_status(self.task_id, 'partial_completed')
            
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {e}")
    
    def _redirect_orchestrator_logs(self, orchestrator):
        """重定向SchemaWorkflowOrchestrator的日志到任务目录"""
        if self.task_dir_logger and hasattr(orchestrator, 'logger'):
            try:
                # 为orchestrator的logger添加任务目录文件处理器
                for handler in self.task_dir_logger.handlers:
                    if isinstance(handler, logging.FileHandler):
                        orchestrator.logger.addHandler(handler)
                        break
            except Exception as e:
                self.logger.error(f"重定向orchestrator日志失败: {e}")
    
    def query_logs_advanced(self,
                           page: int = 1,
                           page_size: int = 50,
                           level: str = None,
                           start_time: str = None,
                           end_time: str = None,
                           keyword: str = None,
                           logger_name: str = None,
                           step_name: str = None,
                           sort_by: str = "timestamp",
                           sort_order: str = "desc") -> dict:
        """
        高级日志查询（工作流层）
        
        Args:
            page: 页码，必须大于0，默认1
            page_size: 每页大小，1-500之间，默认50
            level: 可选，日志级别筛选
            start_time: 可选，开始时间范围
            end_time: 可选，结束时间范围
            keyword: 可选，关键字搜索
            logger_name: 可选，日志记录器名称
            step_name: 可选，执行步骤名称
            sort_by: 可选，排序字段
            sort_order: 可选，排序方向
            
        Returns:
            日志查询结果
        """
        try:
            # 调用数据库层方法
            result = self.task_manager.query_logs_advanced(
                task_id=self.task_id,
                page=page,
                page_size=page_size,
                level=level,
                start_time=start_time,
                end_time=end_time,
                keyword=keyword,
                logger_name=logger_name,
                step_name=step_name,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            # 记录查询操作
            self.logger.info(f"日志查询完成: {self.task_id}, 页码: {page}, 结果数: {len(result.get('logs', []))}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"日志查询失败: {e}")
            return {
                "logs": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False
                },
                "log_file_info": {
                    "exists": False,
                    "error": str(e)
                },
                "query_time": "0.000s"
            }
    
    def cleanup(self):
        """清理资源"""
        try:
            # 清理任务目录日志记录器
            if self.task_dir_logger:
                for handler in self.task_dir_logger.handlers:
                    handler.close()
                self.task_dir_logger.handlers.clear()
                
            self.task_manager.close_connection()
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")


class SimpleWorkflowManager:
    """简化的任务工作流管理器"""
    
    def __init__(self):
        """初始化工作流管理器"""
        self.task_manager = SimpleTaskManager()
        self.file_manager = SimpleFileManager()
        # 使用简单的控制台日志，不使用文件日志
        self.logger = logging.getLogger("SimpleWorkflowManager")
        self.logger.setLevel(logging.INFO)
    
    def create_task(self, 
                   table_list_file: str = None,
                   business_context: str = None,
                   db_name: str = None,
                   **kwargs) -> str:
        """创建新任务"""
        try:
            # 如果提供了table_list_file，验证文件存在
            if table_list_file and not os.path.exists(table_list_file):
                raise FileNotFoundError(f"表清单文件不存在: {table_list_file}")
            
            # 创建任务（使用app_config中的数据库配置）
            task_id = self.task_manager.create_task(
                table_list_file=table_list_file,
                business_context=business_context,
                db_name=db_name,
                **kwargs
            )
            
            return task_id
            
        except Exception as e:
            self.logger.error(f"创建任务失败: {e}")
            raise
    
    async def execute_task(self, 
                          task_id: str,
                          execution_mode: str = "complete",
                          step_name: Optional[str] = None) -> Dict[str, Any]:
        """执行任务"""
        executor = None
        try:
            executor = SimpleWorkflowExecutor(task_id)
            
            if execution_mode == "complete":
                return await executor.execute_complete_workflow()
            elif execution_mode == "step":
                if not step_name:
                    raise ValueError("步骤执行模式需要指定step_name")
                return await executor.execute_single_step(step_name)
            else:
                raise ValueError(f"不支持的执行模式: {execution_mode}")
                
        finally:
            if executor:
                executor.cleanup()
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self.task_manager.get_task(task_id)
    
    def get_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务文件列表"""
        return self.file_manager.get_task_files(task_id)
    
    def get_task_steps(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务步骤状态"""
        return self.task_manager.get_task_steps(task_id)
    
    def get_tasks_list(self, **kwargs) -> List[Dict[str, Any]]:
        """获取任务列表"""
        return self.task_manager.get_tasks_list(**kwargs)
    
    def query_tasks_advanced(self, **kwargs) -> dict:
        """
        高级任务查询，支持复杂筛选、排序、分页
        
        Args:
            **kwargs: 传递给数据库层的查询参数
        
        Returns:
            包含任务列表和分页信息的字典
        """
        return self.task_manager.query_tasks_advanced(**kwargs)
    
    def cleanup(self):
        """清理资源"""
        try:
            self.task_manager.close_connection()
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")