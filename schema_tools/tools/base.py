import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, List
from schema_tools.utils.data_structures import ProcessingResult, TableProcessingContext

class ToolRegistry:
    """工具注册管理器"""
    _tools: Dict[str, Type['BaseTool']] = {}
    _instances: Dict[str, 'BaseTool'] = {}
    
    @classmethod
    def register(cls, name: str):
        """装饰器：注册工具"""
        def decorator(tool_class: Type['BaseTool']):
            cls._tools[name] = tool_class
            logging.debug(f"注册工具: {name} -> {tool_class.__name__}")
            return tool_class
        return decorator
    
    @classmethod
    def get_tool(cls, name: str, **kwargs) -> 'BaseTool':
        """获取工具实例，支持单例模式"""
        if name not in cls._instances:
            if name not in cls._tools:
                raise ValueError(f"工具 '{name}' 未注册")
            
            tool_class = cls._tools[name]
            
            # 自动注入vanna实例到需要LLM的工具
            if hasattr(tool_class, 'needs_llm') and tool_class.needs_llm:
                from core.vanna_llm_factory import create_vanna_instance
                kwargs['vn'] = create_vanna_instance()
                logging.debug(f"为工具 {name} 注入LLM实例")
            
            cls._instances[name] = tool_class(**kwargs)
        
        return cls._instances[name]
    
    @classmethod
    def list_tools(cls) -> List[str]:
        """列出所有已注册的工具"""
        return list(cls._tools.keys())
    
    @classmethod
    def clear_instances(cls):
        """清除所有工具实例（用于测试）"""
        cls._instances.clear()

class BaseTool(ABC):
    """工具基类"""
    
    needs_llm: bool = False  # 是否需要LLM实例
    tool_name: str = ""      # 工具名称
    
    def __init__(self, **kwargs):
        self.logger = logging.getLogger(f"schema_tools.{self.__class__.__name__}")
        
        # 如果工具需要LLM，检查是否已注入
        if self.needs_llm and 'vn' not in kwargs:
            raise ValueError(f"工具 {self.__class__.__name__} 需要LLM实例但未提供")
        
        # 存储vanna实例
        if 'vn' in kwargs:
            self.vn = kwargs['vn']
    
    @abstractmethod
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """
        执行工具逻辑
        Args:
            context: 表处理上下文
        Returns:
            ProcessingResult: 处理结果
        """
        pass
    
    async def _execute_with_timing(self, context: TableProcessingContext) -> ProcessingResult:
        """带计时的执行包装器"""
        start_time = time.time()
        
        try:
            self.logger.info(f"开始执行工具: {self.tool_name}")
            result = await self.execute(context)
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            if result.success:
                self.logger.info(f"工具 {self.tool_name} 执行成功，耗时: {execution_time:.2f}秒")
            else:
                self.logger.error(f"工具 {self.tool_name} 执行失败: {result.error_message}")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.exception(f"工具 {self.tool_name} 执行异常")
            
            return ProcessingResult(
                success=False,
                error_message=f"工具执行异常: {str(e)}",
                execution_time=execution_time
            )
    
    def validate_input(self, context: TableProcessingContext) -> bool:
        """输入验证（子类可重写）"""
        return context.table_metadata is not None


class PipelineExecutor:
    """处理链执行器"""
    
    def __init__(self, pipeline_config: Dict[str, List[str]]):
        self.pipeline_config = pipeline_config
        self.logger = logging.getLogger("schema_tools.PipelineExecutor")
    
    async def execute_pipeline(self, pipeline_name: str, context: TableProcessingContext) -> Dict[str, ProcessingResult]:
        """执行指定的处理链"""
        if pipeline_name not in self.pipeline_config:
            raise ValueError(f"未知的处理链: {pipeline_name}")
        
        steps = self.pipeline_config[pipeline_name]
        results = {}
        
        self.logger.info(f"开始执行处理链 '{pipeline_name}': {' -> '.join(steps)}")
        
        for step_name in steps:
            try:
                tool = ToolRegistry.get_tool(step_name)
                
                # 验证输入
                if not tool.validate_input(context):
                    result = ProcessingResult(
                        success=False,
                        error_message=f"工具 {step_name} 输入验证失败"
                    )
                else:
                    result = await tool._execute_with_timing(context)
                
                results[step_name] = result
                context.update_step(step_name, result)
                
                # 如果步骤失败且不允许继续，则停止
                if not result.success:
                    from schema_tools.config import SCHEMA_TOOLS_CONFIG
                    if not SCHEMA_TOOLS_CONFIG["continue_on_error"]:
                        self.logger.error(f"步骤 {step_name} 失败，停止处理链执行")
                        break
                    else:
                        self.logger.warning(f"步骤 {step_name} 失败，继续执行下一步")
                
            except Exception as e:
                self.logger.exception(f"执行步骤 {step_name} 时发生异常")
                results[step_name] = ProcessingResult(
                    success=False,
                    error_message=f"步骤执行异常: {str(e)}"
                )
                break
        
        return results