"""
Data Pipeline API 简化任务工作流

集成简化后的数据库管理器和文件管理器，提供任务执行功能
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

from data_pipeline.schema_workflow import SchemaWorkflowOrchestrator
from data_pipeline.api.simple_db_manager import SimpleTaskManager
from data_pipeline.api.simple_file_manager import SimpleFileManager
from core.logging import get_data_pipeline_logger


class SimpleWorkflowExecutor:
    """简化的任务工作流执行器"""
    
    def __init__(self, task_id: str):
        """
        初始化工作流执行器
        
        Args:
            task_id: 任务ID
        """
        self.task_id = task_id
        self.logger = get_data_pipeline_logger("SimpleWorkflowExecutor")
        
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
    
    def _create_orchestrator(self) -> SchemaWorkflowOrchestrator:
        """创建工作流编排器"""
        task_dir = self.file_manager.get_task_directory(self.task_id)
        
        return SchemaWorkflowOrchestrator(
            db_connection=self.task_params['db_connection'],
            table_list_file=self.task_params['table_list_file'],
            business_context=self.task_params['business_context'],
            output_dir=str(task_dir),
            enable_sql_validation=self.task_params.get('enable_sql_validation', True),
            enable_llm_repair=self.task_params.get('enable_llm_repair', True),
            modify_original_file=self.task_params.get('modify_original_file', True),
            enable_training_data_load=self.task_params.get('enable_training_data_load', True)
        )
    
    @contextmanager
    def _step_execution(self, step_name: str):
        """步骤执行上下文管理器"""
        execution_id = None
        
        try:
            # 开始执行
            execution_id = self.task_manager.create_execution(self.task_id, step_name)
            self.task_manager.update_step_status(self.task_id, step_name, "running")
            self.task_manager.record_log(self.task_id, "INFO", f"开始执行步骤: {step_name}", execution_id, step_name)
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", f"开始执行步骤: {step_name}", step_name)
            
            yield execution_id
            
            # 成功完成
            self.task_manager.complete_execution(execution_id, 'completed')
            self.task_manager.update_step_status(self.task_id, step_name, "completed")
            self.task_manager.record_log(self.task_id, "INFO", f"步骤执行完成: {step_name}", execution_id, step_name)
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", f"步骤执行完成: {step_name}", step_name)
            
        except Exception as e:
            # 执行失败
            error_msg = str(e)
            
            if execution_id:
                self.task_manager.complete_execution(execution_id, 'failed', error_msg)
            
            self.task_manager.update_step_status(self.task_id, step_name, "failed")
            self.task_manager.record_log(self.task_id, "ERROR", f"步骤执行失败: {step_name} - {error_msg}", execution_id, step_name)
            
            # 记录到任务目录日志
            self._log_to_task_directory("ERROR", f"步骤执行失败: {step_name} - {error_msg}", step_name)
            raise
    
    async def execute_complete_workflow(self) -> Dict[str, Any]:
        """执行完整工作流"""
        try:
            # 确保任务目录存在
            if not self._ensure_task_directory():
                raise Exception("无法创建任务目录")
            
            # 开始任务
            self.task_manager.update_task_status(self.task_id, 'in_progress')
            self.task_manager.record_log(self.task_id, "INFO", "任务开始执行")
            
            # 记录到任务目录日志
            self._log_to_task_directory("INFO", "完整工作流任务开始执行")
            
            # 创建工作流编排器
            orchestrator = self._create_orchestrator()
            
            # 执行完整工作流
            with self._step_execution("complete") as execution_id:
                self.task_manager.record_log(self.task_id, "INFO", "开始执行完整工作流", execution_id, "complete")
                
                # 重定向SchemaWorkflowOrchestrator的日志到任务目录
                self._redirect_orchestrator_logs(orchestrator)
                
                result = await orchestrator.execute_complete_workflow()
                
                # 写入结果文件
                self._write_result_file(result)
                
                self.task_manager.record_log(self.task_id, "INFO", "完整工作流执行完成", execution_id, "complete")
            
            # 更新所有子步骤状态为完成
            self._update_all_step_status_for_complete_workflow(result)
            
            # 完成任务
            self.task_manager.update_task_status(self.task_id, 'completed')
            self.task_manager.record_log(self.task_id, "INFO", "任务执行完成")
            
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
            self.task_manager.record_log(self.task_id, "ERROR", f"任务执行失败: {error_msg}")
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
            # 确保任务目录存在
            if not self._ensure_task_directory():
                raise Exception("无法创建任务目录")
            
            # 更新任务状态
            self.task_manager.update_task_status(self.task_id, 'in_progress')
            
            # 创建工作流编排器
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
            self.task_manager.record_log(self.task_id, "ERROR", f"步骤执行失败: {step_name} - {error_msg}")
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
            executions = self.task_manager.get_task_executions(self.task_id)
            
            completed_steps = set()
            failed_steps = set()
            
            for execution in executions:
                if execution['status'] == 'completed':
                    completed_steps.add(execution['execution_step'])
                elif execution['status'] == 'failed':
                    failed_steps.add(execution['execution_step'])
            
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
    
    def _update_all_step_status_for_complete_workflow(self, result: Dict[str, Any]):
        """完整工作流成功后，更新所有子步骤状态为完成"""
        try:
            # 定义完整工作流包含的所有步骤
            workflow_steps = ["ddl_generation", "qa_generation", "sql_validation", "training_load"]
            
            # 记录日志
            self._log_to_task_directory("INFO", "开始更新完整工作流各步骤状态为完成")
            
            # 逐一更新每个步骤的状态为完成
            for step_name in workflow_steps:
                try:
                    self.task_manager.update_step_status(self.task_id, step_name, "completed")
                    self.task_manager.record_log(
                        self.task_id, 
                        "INFO", 
                        f"完整工作流执行成功，更新步骤状态为完成: {step_name}",
                        step_name=step_name
                    )
                    self._log_to_task_directory("INFO", f"更新步骤状态为完成: {step_name}", step_name)
                except Exception as step_error:
                    self.logger.error(f"更新步骤状态失败 {step_name}: {step_error}")
                    self._log_to_task_directory("ERROR", f"更新步骤状态失败: {step_name} - {step_error}", step_name)
            
            self._log_to_task_directory("INFO", "完整工作流各步骤状态更新完成")
            
        except Exception as e:
            self.logger.error(f"更新完整工作流步骤状态失败: {e}")
            self._log_to_task_directory("ERROR", f"更新完整工作流步骤状态失败: {e}")
    
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
        self.logger = get_data_pipeline_logger("SimpleWorkflowManager")
    
    def create_task(self, 
                   table_list_file: str,
                   business_context: str,
                   db_name: str = None,
                   **kwargs) -> str:
        """创建新任务"""
        try:
            # 验证表清单文件存在
            if not os.path.exists(table_list_file):
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
    
    def get_task_logs(self, task_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取任务日志"""
        return self.task_manager.get_task_logs(task_id, limit)
    
    def get_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务文件列表"""
        return self.file_manager.get_task_files(task_id)
    
    def get_task_executions(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务执行记录"""
        return self.task_manager.get_task_executions(task_id)
    
    def get_tasks_list(self, **kwargs) -> List[Dict[str, Any]]:
        """获取任务列表"""
        return self.task_manager.get_tasks_list(**kwargs)
    
    def cleanup(self):
        """清理资源"""
        try:
            self.task_manager.close_connection()
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")