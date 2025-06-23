# Schema Tools 详细设计文档

## 1. 项目结构与模块设计

### 1.1 完整目录结构

```
schema_tools/
├── __init__.py                     # 模块入口，导出主要接口
├── __main__.py                     # 命令行入口
├── config.py                       # 配置管理
├── training_data_agent.py          # 主AI Agent
├── tools/                          # Agent工具集
│   ├── __init__.py                 # 工具模块初始化
│   ├── base.py                     # 基础工具类和注册机制
│   ├── database_inspector.py       # 数据库元数据检查工具
│   ├── data_sampler.py             # 数据采样工具
│   ├── comment_generator.py        # LLM注释生成工具
│   ├── ddl_generator.py            # DDL格式生成工具
│   └── doc_generator.py            # MD文档生成工具
├── utils/                          # 工具函数
│   ├── __init__.py
│   ├── data_structures.py          # 数据结构定义
│   ├── table_parser.py             # 表清单解析器
│   ├── file_manager.py             # 文件管理器
│   ├── system_filter.py            # 系统表过滤器
│   ├── permission_checker.py       # 权限检查器
│   ├── large_table_handler.py      # 大表处理器
│   └── logger.py                   # 日志管理
├── prompts/                        # 提示词模板
│   ├── table_comment_template.txt
│   ├── field_comment_template.txt
│   ├── enum_detection_template.txt
│   ├── business_context.txt
│   └── business_dictionary.txt
└── tests/                          # 测试用例
    ├── unit/
    ├── integration/
    └── fixtures/
```

## 2. 核心数据结构设计

### 2.1 数据结构定义 (`utils/data_structures.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
import hashlib
import json

class FieldType(Enum):
    """字段类型枚举"""
    INTEGER = "integer"
    VARCHAR = "varchar"
    TEXT = "text"
    TIMESTAMP = "timestamp"
    DATE = "date"
    BOOLEAN = "boolean"
    NUMERIC = "numeric"
    ENUM = "enum"
    JSON = "json"
    UUID = "uuid"
    OTHER = "other"

class ProcessingStatus(Enum):
    """处理状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class FieldInfo:
    """字段信息标准结构"""
    name: str
    type: str
    nullable: bool
    default_value: Optional[str] = None
    comment: Optional[str] = None
    original_comment: Optional[str] = None  # 原始注释
    generated_comment: Optional[str] = None  # LLM生成的注释
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_enum: bool = False
    enum_values: Optional[List[str]] = None
    enum_description: Optional[str] = None
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'type': self.type,
            'nullable': self.nullable,
            'default_value': self.default_value,
            'comment': self.comment,
            'is_primary_key': self.is_primary_key,
            'is_foreign_key': self.is_foreign_key,
            'is_enum': self.is_enum,
            'enum_values': self.enum_values
        }

@dataclass
class TableMetadata:
    """表元数据标准结构"""
    schema_name: str
    table_name: str
    full_name: str  # schema.table_name
    comment: Optional[str] = None
    original_comment: Optional[str] = None  # 原始注释
    generated_comment: Optional[str] = None  # LLM生成的注释
    fields: List[FieldInfo] = field(default_factory=list)
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    row_count: Optional[int] = None
    table_size: Optional[str] = None  # 表大小（如 "1.2 MB"）
    created_date: Optional[str] = None
    
    @property
    def safe_file_name(self) -> str:
        """生成安全的文件名"""
        if self.schema_name.lower() == 'public':
            return self.table_name
        return f"{self.schema_name}__{self.table_name}".replace('.', '__').replace('-', '_').replace(' ', '_')
    
    def get_metadata_hash(self) -> str:
        """计算元数据哈希值，用于增量更新判断"""
        hash_data = {
            'schema_name': self.schema_name,
            'table_name': self.table_name,
            'fields': [f.to_dict() for f in self.fields],
            'comment': self.original_comment
        }
        return hashlib.md5(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()

@dataclass
class ProcessingResult:
    """工具处理结果标准结构"""
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    execution_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_warning(self, warning: str):
        """添加警告信息"""
        self.warnings.append(warning)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'success': self.success,
            'data': self.data,
            'error_message': self.error_message,
            'warnings': self.warnings,
            'execution_time': self.execution_time,
            'metadata': self.metadata
        }

@dataclass
class TableProcessingContext:
    """表处理上下文"""
    table_metadata: TableMetadata
    business_context: str
    output_dir: str
    pipeline: str
    vn: Any  # vanna实例
    file_manager: Any
    current_step: str = "initialized"
    step_results: Dict[str, ProcessingResult] = field(default_factory=dict)
    start_time: Optional[float] = None
    
    def update_step(self, step_name: str, result: ProcessingResult):
        """更新步骤结果"""
        self.current_step = step_name
        self.step_results[step_name] = result
```

## 3. 工具注册与管理系统

### 3.1 基础工具类 (`tools/base.py`)

```python
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from utils.data_structures import ProcessingResult, TableProcessingContext

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
```

### 3.2 Pipeline执行器 (`training_data_agent.py` 的一部分)

```python
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
                    from config import SCHEMA_TOOLS_CONFIG
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
```

## 4. 核心工具实现

### 4.1 数据库检查工具 (`tools/database_inspector.py`)

```python
import asyncio
import asyncpg
from typing import List, Dict, Any, Optional
from tools.base import BaseTool, ToolRegistry
from utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo, TableMetadata

@ToolRegistry.register("database_inspector")
class DatabaseInspectorTool(BaseTool):
    """数据库元数据检查工具"""
    
    needs_llm = False
    tool_name = "数据库检查器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db_connection = kwargs.get('db_connection')
        self.connection_pool = None
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行数据库元数据检查"""
        try:
            # 建立数据库连接
            if not self.connection_pool:
                await self._create_connection_pool()
            
            table_name = context.table_metadata.table_name
            schema_name = context.table_metadata.schema_name
            
            # 获取表的基本信息
            table_info = await self._get_table_info(schema_name, table_name)
            if not table_info:
                return ProcessingResult(
                    success=False,
                    error_message=f"表 {schema_name}.{table_name} 不存在或无权限访问"
                )
            
            # 获取字段信息
            fields = await self._get_table_fields(schema_name, table_name)
            
            # 获取表注释
            table_comment = await self._get_table_comment(schema_name, table_name)
            
            # 获取表统计信息
            stats = await self._get_table_statistics(schema_name, table_name)
            
            # 更新表元数据
            context.table_metadata.original_comment = table_comment
            context.table_metadata.comment = table_comment
            context.table_metadata.fields = fields
            context.table_metadata.row_count = stats.get('row_count')
            context.table_metadata.table_size = stats.get('table_size')
            
            return ProcessingResult(
                success=True,
                data={
                    'fields_count': len(fields),
                    'table_comment': table_comment,
                    'row_count': stats.get('row_count'),
                    'table_size': stats.get('table_size')
                },
                metadata={'tool': self.tool_name}
            )
            
        except Exception as e:
            self.logger.exception(f"数据库检查失败")
            return ProcessingResult(
                success=False,
                error_message=f"数据库检查失败: {str(e)}"
            )
    
    async def _create_connection_pool(self):
        """创建数据库连接池"""
        try:
            self.connection_pool = await asyncpg.create_pool(
                self.db_connection,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
            self.logger.info("数据库连接池创建成功")
        except Exception as e:
            self.logger.error(f"创建数据库连接池失败: {e}")
            raise
    
    async def _get_table_info(self, schema_name: str, table_name: str) -> Optional[Dict]:
        """获取表基本信息"""
        query = """
        SELECT schemaname, tablename, tableowner, tablespace, hasindexes, hasrules, hastriggers
        FROM pg_tables 
        WHERE schemaname = $1 AND tablename = $2
        """
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchrow(query, schema_name, table_name)
            return dict(result) if result else None
    
    async def _get_table_fields(self, schema_name: str, table_name: str) -> List[FieldInfo]:
        """获取表字段信息"""
        query = """
        SELECT 
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            pd.description as column_comment,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
            CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key
        FROM information_schema.columns c
        LEFT JOIN pg_description pd ON pd.objsubid = c.ordinal_position 
            AND pd.objoid = (
                SELECT oid FROM pg_class 
                WHERE relname = c.table_name 
                AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = c.table_schema)
            )
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.table_schema = $1 AND tc.table_name = $2 AND tc.constraint_type = 'PRIMARY KEY'
        ) pk ON pk.column_name = c.column_name
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.table_schema = $1 AND tc.table_name = $2 AND tc.constraint_type = 'FOREIGN KEY'
        ) fk ON fk.column_name = c.column_name
        WHERE c.table_schema = $1 AND c.table_name = $2
        ORDER BY c.ordinal_position
        """
        
        fields = []
        async with self.connection_pool.acquire() as conn:
            rows = await conn.fetch(query, schema_name, table_name)
            
            for row in rows:
                field = FieldInfo(
                    name=row['column_name'],
                    type=row['data_type'],
                    nullable=row['is_nullable'] == 'YES',
                    default_value=row['column_default'],
                    original_comment=row['column_comment'],
                    comment=row['column_comment'],
                    is_primary_key=row['is_primary_key'],
                    is_foreign_key=row['is_foreign_key'],
                    max_length=row['character_maximum_length'],
                    precision=row['numeric_precision'],
                    scale=row['numeric_scale']
                )
                fields.append(field)
        
        return fields
    
    async def _get_table_comment(self, schema_name: str, table_name: str) -> Optional[str]:
        """获取表注释"""
        query = """
        SELECT obj_description(oid) as table_comment
        FROM pg_class 
        WHERE relname = $2 
        AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $1)
        """
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchval(query, schema_name, table_name)
            return result
    
    async def _get_table_statistics(self, schema_name: str, table_name: str) -> Dict[str, Any]:
        """获取表统计信息"""
        stats_query = """
        SELECT 
            schemaname,
            tablename,
            attname,
            n_distinct,
            most_common_vals,
            most_common_freqs,
            histogram_bounds
        FROM pg_stats 
        WHERE schemaname = $1 AND tablename = $2
        """
        
        size_query = """
        SELECT pg_size_pretty(pg_total_relation_size($1)) as table_size,
               pg_relation_size($1) as table_size_bytes
        """
        
        count_query = f"SELECT COUNT(*) as row_count FROM {schema_name}.{table_name}"
        
        stats = {}
        async with self.connection_pool.acquire() as conn:
            try:
                # 获取行数
                row_count = await conn.fetchval(count_query)
                stats['row_count'] = row_count
                
                # 获取表大小
                table_oid = await conn.fetchval(
                    "SELECT oid FROM pg_class WHERE relname = $1 AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $2)",
                    table_name, schema_name
                )
                if table_oid:
                    size_result = await conn.fetchrow(size_query, table_oid)
                    stats['table_size'] = size_result['table_size']
                    stats['table_size_bytes'] = size_result['table_size_bytes']
                
            except Exception as e:
                self.logger.warning(f"获取表统计信息失败: {e}")
        
        return stats
```

### 4.2 数据采样工具 (`tools/data_sampler.py`)

```python
import random
from typing import List, Dict, Any
from tools.base import BaseTool, ToolRegistry
from utils.data_structures import ProcessingResult, TableProcessingContext

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
            from config import SCHEMA_TOOLS_CONFIG
            
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
        from tools.database_inspector import DatabaseInspectorTool
        
        # 复用数据库检查工具的连接
        inspector = ToolRegistry.get_tool("database_inspector")
        
        query = f"SELECT * FROM {table_metadata.full_name} LIMIT {limit}"
        
        async with inspector.connection_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    async def _smart_sample_large_table(self, table_metadata: TableMetadata, limit: int) -> List[Dict[str, Any]]:
        """智能采样策略（用于大表）"""
        from tools.database_inspector import DatabaseInspectorTool
        
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
```

### 4.3 LLM注释生成工具 (`tools/comment_generator.py`)

~~~python
import asyncio
from typing import List, Dict, Any, Tuple
from tools.base import BaseTool, ToolRegistry
from utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo

@ToolRegistry.register("comment_generator")
class CommentGeneratorTool(BaseTool):
    """LLM注释生成工具"""
    
    needs_llm = True
    tool_name = "注释生成器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.business_context = kwargs.get('business_context', '')
        self.business_dictionary = self._load_business_dictionary()
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行注释生成"""
        try:
            table_metadata = context.table_metadata
            
            # 生成表注释
            table_comment_result = await self._generate_table_comment(table_metadata, context.business_context)
            
            # 生成字段注释和枚举建议
            field_results = await self._generate_field_comments_and_enums(table_metadata, context.business_context)
            
            # 更新表元数据
            if table_comment_result['success']:
                table_metadata.generated_comment = table_comment_result['comment']
                table_metadata.comment = table_comment_result['comment']
            
            # 更新字段信息
            enum_suggestions = []
            for i, field in enumerate(table_metadata.fields):
                if i < len(field_results) and field_results[i]['success']:
                    field.generated_comment = field_results[i]['comment']
                    field.comment = field_results[i]['comment']
                    
                    # 处理枚举建议
                    if field_results[i].get('is_enum'):
                        field.is_enum = True
                        enum_suggestions.append({
                            'field_name': field.name,
                            'suggested_values': field_results[i].get('enum_values', []),
                            'enum_description': field_results[i].get('enum_description', '')
                        })
            
            # 验证枚举建议
            if enum_suggestions:
                validated_enums = await self._validate_enum_suggestions(table_metadata, enum_suggestions)
                
                # 更新验证后的枚举信息
                for enum_info in validated_enums:
                    field_name = enum_info['field_name']
                    for field in table_metadata.fields:
                        if field.name == field_name:
                            field.enum_values = enum_info['actual_values']
                            field.enum_description = enum_info['description']
                            break
            
            return ProcessingResult(
                success=True,
                data={
                    'table_comment_generated': table_comment_result['success'],
                    'field_comments_generated': sum(1 for r in field_results if r['success']),
                    'enum_fields_detected': len([f for f in table_metadata.fields if f.is_enum]),
                    'enum_suggestions': enum_suggestions
                },
                metadata={'tool': self.tool_name}
            )
            
        except Exception as e:
            self.logger.exception(f"注释生成失败")
            return ProcessingResult(
                success=False,
                error_message=f"注释生成失败: {str(e)}"
            )
    
    async def _generate_table_comment(self, table_metadata, business_context: str) -> Dict[str, Any]:
        """生成表注释"""
        try:
            prompt = self._build_table_comment_prompt(table_metadata, business_context)
            
            # 调用LLM
            response = await self._call_llm_with_retry(prompt)
            
            # 解析响应
            comment = self._extract_table_comment(response)
            
            return {
                'success': True,
                'comment': comment,
                'original_response': response
            }
            
        except Exception as e:
            self.logger.error(f"表注释生成失败: {e}")
            return {
                'success': False,
                'comment': table_metadata.original_comment or f"{table_metadata.table_name}表",
                'error': str(e)
            }
    
    async def _generate_field_comments_and_enums(self, table_metadata, business_context: str) -> List[Dict[str, Any]]:
        """批量生成字段注释和枚举建议"""
        try:
            # 构建批量处理的提示词
            prompt = self._build_field_batch_prompt(table_metadata, business_context)
            
            # 调用LLM
            response = await self._call_llm_with_retry(prompt)
            
            # 解析批量响应
            field_results = self._parse_field_batch_response(response, table_metadata.fields)
            
            return field_results
            
        except Exception as e:
            self.logger.error(f"字段注释批量生成失败: {e}")
            # 返回默认结果
            return [
                {
                    'success': False,
                    'comment': field.original_comment or field.name,
                    'is_enum': False,
                    'error': str(e)
                }
                for field in table_metadata.fields
            ]
    
    def _build_table_comment_prompt(self, table_metadata, business_context: str) -> str:
        """构建表注释生成提示词"""
        # 准备字段信息摘要
        fields_summary = []
        for field in table_metadata.fields[:10]:  # 只显示前10个字段避免过长
            field_desc = f"- {field.name} ({field.type})"
            if field.comment:
                field_desc += f": {field.comment}"
            fields_summary.append(field_desc)
        
        # 准备样例数据摘要
        sample_summary = ""
        if table_metadata.sample_data:
            sample_count = min(3, len(table_metadata.sample_data))
            sample_summary = f"\n样例数据({sample_count}条):\n"
            for i, sample in enumerate(table_metadata.sample_data[:sample_count]):
                sample_str = ", ".join([f"{k}={v}" for k, v in list(sample.items())[:5]])
                sample_summary += f"{i+1}. {sample_str}\n"
        
        prompt = f"""你是一个数据库文档专家。请根据以下信息为数据库表生成简洁、准确的中文注释。

业务背景: {business_context}
{self.business_dictionary}

表信息:
- 表名: {table_metadata.table_name}
- Schema: {table_metadata.schema_name}
- 现有注释: {table_metadata.original_comment or "无"}
- 字段数量: {len(table_metadata.fields)}
- 数据行数: {table_metadata.row_count or "未知"}

主要字段:
{chr(10).join(fields_summary)}

{sample_summary}

请生成一个简洁、准确的中文表注释，要求:
1. 如果现有注释是英文，请翻译为中文并改进
2. 根据字段名称和样例数据推断表的业务用途
3. 注释长度控制在50字以内
4. 突出表的核心业务价值

表注释:"""
        
        return prompt
    
    def _build_field_batch_prompt(self, table_metadata, business_context: str) -> str:
        """构建字段批量处理提示词"""
        # 准备字段信息
        fields_info = []
        sample_values = {}
        
        # 收集字段的样例值
        for sample in table_metadata.sample_data[:5]:
            for field_name, value in sample.items():
                if field_name not in sample_values:
                    sample_values[field_name] = []
                if value is not None and len(sample_values[field_name]) < 5:
                    sample_values[field_name].append(str(value))
        
        # 构建字段信息列表
        for field in table_metadata.fields:
            field_info = f"{field.name} ({field.type})"
            if field.original_comment:
                field_info += f" - 原注释: {field.original_comment}"
            
            # 添加样例值
            if field.name in sample_values and sample_values[field.name]:
                values_str = ", ".join(sample_values[field.name][:3])
                field_info += f" - 样例值: {values_str}"
            
            fields_info.append(field_info)
        
        prompt = f"""你是一个数据库文档专家。请为以下表的所有字段生成中文注释，并识别可能的枚举字段。

业务背景: {business_context}
{self.business_dictionary}

表名: {table_metadata.schema_name}.{table_metadata.table_name}
表注释: {table_metadata.comment or "无"}

字段列表:
{chr(10).join([f"{i+1}. {info}" for i, info in enumerate(fields_info)])}

请按以下JSON格式输出每个字段的分析结果:
```json
{{
  "fields": [
    {{
      "name": "字段名",
      "comment": "中文注释（简洁明确，15字以内）",
      "is_enum": true/false,
      "enum_values": ["值1", "值2", "值3"] (如果是枚举),
      "enum_description": "枚举含义说明" (如果是枚举)
    }}
  ]
}}
~~~

注释生成要求:

1. 如果原注释是英文，翻译为中文并改进
2. 根据字段名、类型和样例值推断字段含义
3. 识别可能的枚举字段（如状态、类型、级别等）
4. 枚举判断标准: VARCHAR类型 + 样例值重复度高 + 字段名暗示分类
5. 注释要贴近{business_context}的业务场景

请输出JSON格式的分析结果:"""

```
    return prompt

async def _call_llm_with_retry(self, prompt: str, max_retries: int = 3) -> str:
    """带重试的LLM调用"""
    from config import SCHEMA_TOOLS_CONFIG
    
    for attempt in range(max_retries):
        try:
            # 使用vanna实例调用LLM
            response = await asyncio.to_thread(self.vn.ask, prompt)
            
            if response and response.strip():
                return response.strip()
            else:
                raise ValueError("LLM返回空响应")
                
        except Exception as e:
            self.logger.warning(f"LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1)  # 等待1秒后重试
    
    raise Exception("LLM调用达到最大重试次数")

def _extract_table_comment(self, llm_response: str) -> str:
    """从LLM响应中提取表注释"""
    # 简单的文本清理和提取逻辑
    lines = llm_response.strip().split('\n')
    
    # 查找包含实际注释的行
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('*'):
            # 移除可能的前缀
            prefixes = ['表注释:', '注释:', '说明:', '表说明:']
            for prefix in prefixes:
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
            
            if line:
                return line[:200]  # 限制长度
    
    return llm_response.strip()[:200]

def _parse_field_batch_response(self, llm_response: str, fields: List[FieldInfo]) -> List[Dict[str, Any]]:
    """解析字段批量处理响应"""
    import json
    import re
    
    try:
        # 尝试提取JSON部分
        json_match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 如果没有代码块，尝试直接解析
            json_str = llm_response
        
        # 解析JSON
        parsed_data = json.loads(json_str)
        field_data = parsed_data.get('fields', [])
        
        # 映射到字段结果
        results = []
        for i, field in enumerate(fields):
            if i < len(field_data):
                data = field_data[i]
                results.append({
                    'success': True,
                    'comment': data.get('comment', field.name),
                    'is_enum': data.get('is_enum', False),
                    'enum_values': data.get('enum_values', []),
                    'enum_description': data.get('enum_description', '')
                })
            else:
                # 默认结果
                results.append({
                    'success': False,
                    'comment': field.original_comment or field.name,
                    'is_enum': False
                })
        
        return results
        
    except Exception as e:
        self.logger.error(f"解析字段批量响应失败: {e}")
        # 返回默认结果
        return [
            {
                'success': False,
                'comment': field.original_comment or field.name,
                'is_enum': False,
                'error': str(e)
            }
            for field in fields
        ]

async def _validate_enum_suggestions(self, table_metadata, enum_suggestions: List[Dict]) -> List[Dict]:
    """验证枚举建议"""
    from tools.database_inspector import DatabaseInspectorTool
    from config import SCHEMA_TOOLS_CONFIG
    
    validated_enums = []
    inspector = ToolRegistry.get_tool("database_inspector")
    sample_limit = SCHEMA_TOOLS_CONFIG["enum_detection_sample_limit"]
    
    for enum_info in enum_suggestions:
        field_name = enum_info['field_name']
        
        try:
            # 查询字段的所有不同值
            query = f"""
            SELECT DISTINCT {field_name} as value, COUNT(*) as count
            FROM {table_metadata.full_name}
            WHERE {field_name} IS NOT NULL
            GROUP BY {field_name}
            ORDER BY count DESC
            LIMIT {sample_limit}
            """
            
            async with inspector.connection_pool.acquire() as conn:
                rows = await conn.fetch(query)
                
                actual_values = [str(row['value']) for row in rows]
                
                # 验证是否真的是枚举（不同值数量合理）
                max_enum_values = SCHEMA_TOOLS_CONFIG["enum_max_distinct_values"]
                if len(actual_values) <= max_enum_values:
                    validated_enums.append({
                        'field_name': field_name,
                        'actual_values': actual_values,
                        'suggested_values': enum_info['suggested_values'],
                        'description': enum_info['enum_description'],
                        'value_counts': [(row['value'], row['count']) for row in rows]
                    })
                    self.logger.info(f"确认字段 {field_name} 为枚举类型，包含 {len(actual_values)} 个值")
                else:
                    self.logger.info(f"字段 {field_name} 不同值过多({len(actual_values)})，不认为是枚举")
                    
        except Exception as e:
            self.logger.warning(f"验证字段 {field_name} 的枚举建议失败: {e}")
    
    return validated_enums

def _load_business_dictionary(self) -> str:
    """加载业务词典"""
    try:
        import os
        dict_file = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'business_dictionary.txt')
        if os.path.exists(dict_file):
            with open(dict_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                return f"\n业务词典:\n{content}\n" if content else ""
        return ""
    except Exception as e:
        self.logger.warning(f"加载业务词典失败: {e}")
        return ""
## 5. 主AI Agent实现

### 5.1 主Agent核心代码 (`training_data_agent.py`)

```python
import asyncio
import time
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from tools.base import ToolRegistry, PipelineExecutor
from utils.data_structures import TableMetadata, TableProcessingContext, ProcessingResult
from utils.file_manager import FileNameManager
from utils.system_filter import SystemTableFilter
from utils.permission_checker import DatabasePermissionChecker
from utils.table_parser import TableListParser
from utils.logger import setup_logging

class SchemaTrainingDataAgent:
    """Schema训练数据生成AI Agent"""
    
    def __init__(self, 
                 db_connection: str,
                 table_list_file: str,
                 business_context: str = None,
                 output_dir: str = None,
                 pipeline: str = "full"):
        
        self.db_connection = db_connection
        self.table_list_file = table_list_file
        self.business_context = business_context or "数据库管理系统"
        self.pipeline = pipeline
        
        # 配置管理
        from config import SCHEMA_TOOLS_CONFIG
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
        self.logger = logging.getLogger("schema_tools.Agent")
    
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
            
            # 6. 生成总结报告
            report = self._generate_summary_report(results)
            
            self.stats['end_time'] = time.time()
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
            os.makedirs(os.path.join(self.output_dir, "logs"), exist_ok=True)
        
        # 初始化数据库工具
        database_tool = ToolRegistry.get_tool("database_inspector", db_connection=self.db_connection)
        await database_tool._create_connection_pool()
        
        self.logger.info(f"初始化完成，输出目录: {self.output_dir}")
    
    async def _check_database_permissions(self):
        """检查数据库权限"""
        if not self.config["check_permissions"]:
            return
        
        inspector = ToolRegistry.get_tool("database_inspector")
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
                'files_generated': len(successful_results) * (2 if self.pipeline == 'full' else 1)
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
        self.logger.info(f"  📁 生成文件: {report['statistics']['files_generated']} 个")
        self.logger.info(f"  🕐 总耗时: {total_time:.2f} 秒")
        
        if self.failed_tables:
            self.logger.warning(f"❌ 失败的表: {', '.join(self.failed_tables)}")
        
        return report
    
    async def check_database_permissions(self) -> Dict[str, bool]:
        """检查数据库权限（供外部调用）"""
        inspector = ToolRegistry.get_tool("database_inspector", db_connection=self.db_connection)
        checker = DatabasePermissionChecker(inspector)
        return await checker.check_permissions()
```

## 6. 命令行接口实现

### 6.1 命令行入口 (`__main__.py`)

```python
import argparse
import asyncio
import sys
import os
import logging
from pathlib import Path

def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='Schema Tools - 自动生成数据库训练数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本使用
  python -m schema_tools --db-connection "postgresql://user:pass@host:5432/db" --table-list tables.txt
  
  # 指定业务上下文和输出目录
  python -m schema_tools --db-connection "..." --table-list tables.txt --business-context "电商系统" --output-dir output
  
  # 仅生成DDL文件
  python -m schema_tools --db-connection "..." --table-list tables.txt --pipeline ddl_only
  
  # 权限检查模式
  python -m schema_tools --db-connection "..." --check-permissions-only
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--db-connection',
        required=True,
        help='数据库连接字符串 (例如: postgresql://user:pass@localhost:5432/dbname)'
    )
    
    # 可选参数
    parser.add_argument(
        '--table-list',
        help='表清单文件路径'
    )
    
    parser.add_argument(
        '--business-context',
        help='业务上下文描述'
    )
    
    parser.add_argument(
        '--business-context-file',
        help='业务上下文文件路径'
    )
    
    parser.add_argument(
        '--output-dir',
        help='输出目录路径'
    )
    
    parser.add_argument(
        '--pipeline',
        choices=['full', 'ddl_only', 'analysis_only'],
        help='处理链类型'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        help='最大并发表数量'
    )
    
    # 功能开关
    parser.add_argument(
        '--no-filter-system-tables',
        action='store_true',
        help='禁用系统表过滤'
    )
    
    parser.add_argument(
        '--check-permissions-only',
        action='store_true',
        help='仅检查数据库权限，不处理表'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细日志输出'
    )
    
    parser.add_argument(
        '--log-file',
        help='日志文件路径'
    )
    
    return parser

def load_config_with_overrides(args):
    """加载配置并应用命令行覆盖"""
    from config import SCHEMA_TOOLS_CONFIG
    
    config = SCHEMA_TOOLS_CONFIG.copy()
    
    # 命令行参数覆盖配置
    if args.output_dir:
        config["output_directory"] = args.output_dir
    
    if args.pipeline:
        config["default_pipeline"] = args.pipeline
    
    if args.max_concurrent:
        config["max_concurrent_tables"] = args.max_concurrent
    
    if args.no_filter_system_tables:
        config["filter_system_tables"] = False
    
    if args.log_file:
        config["log_file"] = args.log_file
    
    return config

def load_business_context(args):
    """加载业务上下文"""
    if args.business_context_file:
        try:
            with open(args.business_context_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"警告: 无法读取业务上下文文件 {args.business_context_file}: {e}")
    
    if args.business_context:
        return args.business_context
    
    from config import SCHEMA_TOOLS_CONFIG
    return SCHEMA_TOOLS_CONFIG.get("default_business_context", "数据库管理系统")

async def check_permissions_only(db_connection: str):
    """仅检查数据库权限"""
    from training_data_agent import SchemaTrainingDataAgent
    
    print("🔍 检查数据库权限...")
    
    try:
        agent = SchemaTrainingDataAgent(
            db_connection=db_connection,
            table_list_file="",  # 不需要表清单
            business_context=""   # 不需要业务上下文
        )
        
        # 初始化Agent以建立数据库连接
        await agent._initialize()
        
        # 检查权限
        permissions = await agent.check_database_permissions()
        
        print("\n📋 权限检查结果:")
        print(f"  ✅ 数据库连接: {'可用' if permissions['connect'] else '不可用'}")
        print(f"  ✅ 元数据查询: {'可用' if permissions['select_metadata'] else '不可用'}")
        print(f"  ✅ 数据查询: {'可用' if permissions['select_data'] else '不可用'}")
        print(f"  ℹ️  数据库类型: {'只读' if permissions['is_readonly'] else '读写'}")
        
        if all(permissions.values()):
            print("\n✅ 数据库权限检查通过，可以开始处理")
            return True
        else:
            print("\n❌ 数据库权限不足，请检查配置")
            return False
            
    except Exception as e:
        print(f"\n❌ 权限检查失败: {e}")
        return False

async def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    from utils.logger import setup_logging
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 仅权限检查模式
    if args.check_permissions_only:
        success = await check_permissions_only(args.db_connection)
        sys.exit(0 if success else 1)
    
    # 验证必需参数
    if not args.table_list:
        print("错误: 需要指定 --table-list 参数")
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(args.table_list):
        print(f"错误: 表清单文件不存在: {args.table_list}")
        sys.exit(1)
    
    try:
        # 加载配置和业务上下文
        config = load_config_with_overrides(args)
        business_context = load_business_context(args)
        
        # 创建Agent
        from training_data_agent import SchemaTrainingDataAgent
        
        agent = SchemaTrainingDataAgent(
            db_connection=args.db_connection,
            table_list_file=args.table_list,
            business_context=business_context,
            output_dir=config["output_directory"],
            pipeline=config["default_pipeline"]
        )
        
        # 执行生成
        print("🚀 开始生成Schema训练数据...")
        report = await agent.generate_training_data()
        
        # 输出结果
        if report['summary']['failed'] == 0:
            print("\n🎉 所有表处理成功!")
        else:
            print(f"\n⚠️  处理完成，但有 {report['summary']['failed']} 个表失败")
        
        print(f"📁 输出目录: {config['output_directory']}")
        
        # 如果有失败的表，返回非零退出码
        sys.exit(1 if report['summary']['failed'] > 0 else 0)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断，程序退出")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 程序执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.2 实际输出样例（基于高速公路服务区业务）

#### 6.2.1 DDL文件输出样例 (`bss_service_area.ddl`)

sql

```sql
-- 中文名: 服务区基础信息表
-- 描述: 记录高速公路服务区的基础属性，包括服务区编码、名称、方向、公司归属、地理位置、服务类型和状态，是业务分析与服务区定位的核心表。
create table bss_service_area (
  id varchar(32) not null,              -- 服务区唯一标识（主键，UUID格式）
  version integer not null,             -- 数据版本号
  create_ts timestamp(3),               -- 创建时间
  created_by varchar(50),               -- 创建人
  update_ts timestamp(3),               -- 更新时间
  updated_by varchar(50),               -- 更新人
  delete_ts timestamp(3),               -- 删除时间
  deleted_by varchar(50),               -- 删除人
  service_area_name varchar(255),       -- 服务区名称
  service_area_no varchar(255),         -- 服务区编码（业务唯一标识）
  company_id varchar(32),               -- 公司ID（外键关联bss_company.id）
  service_position varchar(255),        -- 经纬度坐标
  service_area_type varchar(50),        -- 服务区类型（枚举：信息化服务区、智能化服务区）
  service_state varchar(50),            -- 服务区状态（枚举：开放、关闭、上传数据）
  primary key (id)
);
```

#### 6.2.2 MD文档输出样例 (`bss_service_area_detail.md`)

markdown

```markdown
## bss_service_area（服务区基础信息表）
bss_service_area 表记录高速公路服务区的基础属性，包括服务区编码、名称、方向、公司归属、地理位置、服务类型和状态，是业务分析与服务区定位的核心表。

字段列表：
- id (varchar(32)) - 服务区唯一标识（主键，UUID格式）[示例: 0271d68ef93de9684b7ad8c7aae600b6]
- version (integer) - 数据版本号 [示例: 3]
- create_ts (timestamp(3)) - 创建时间 [示例: 2021-05-21 13:26:40.589]
- created_by (varchar(50)) - 创建人 [示例: admin]
- update_ts (timestamp(3)) - 更新时间 [示例: 2021-07-10 15:41:28.795]
- updated_by (varchar(50)) - 更新人 [示例: admin]
- delete_ts (timestamp(3)) - 删除时间
- deleted_by (varchar(50)) - 删除人
- service_area_name (varchar(255)) - 服务区名称 [示例: 鄱阳湖服务区]
- service_area_no (varchar(255)) - 服务区编码（业务唯一标识）[示例: H0509]
- company_id (varchar(32)) - 公司ID（外键关联bss_company.id）[示例: b1629f07c8d9ac81494fbc1de61f1ea5]
- service_position (varchar(255)) - 经纬度坐标 [示例: 114.574721,26.825584]
- service_area_type (varchar(50)) - 服务区类型（枚举：信息化服务区、智能化服务区）[示例: 信息化服务区]
- service_state (varchar(50)) - 服务区状态（枚举：开放、关闭、上传数据）[示例: 开放]

字段补充说明：
- id 为主键，使用 UUID 编码，唯一标识每个服务区
- company_id 外键关联服务区管理公司表(bss_company.id)
- service_position 经纬度格式为"经度,纬度"
- service_area_type 为枚举字段，包含两个取值：信息化服务区、智能化服务区
- service_state 为枚举字段，包含三个取值：开放、关闭、上传数据
- 本表是多个表(bss_branch, bss_car_day_count等)的核心关联实体
```

#### 6.2.3 复杂表样例 (`bss_business_day_data.ddl`)

sql

```sql
-- 中文名: 档口日营业数据表
-- 描述: 记录每天每个档口的营业情况，包含微信、支付宝、现金、金豆等支付方式的金额与订单数，是核心交易数据表。
create table bss_business_day_data (
  id varchar(32) not null,        -- 主键ID
  version integer not null,       -- 数据版本号
  create_ts timestamp(3),         -- 创建时间
  created_by varchar(50),         -- 创建人
  update_ts timestamp(3),         -- 更新时间
  updated_by varchar(50),         -- 更新人
  delete_ts timestamp(3),         -- 删除时间
  deleted_by varchar(50),         -- 删除人
  oper_date date,                 -- 统计日期
  service_no varchar(255),        -- 服务区编码
  service_name varchar(255),      -- 服务区名称
  branch_no varchar(255),         -- 档口编码
  branch_name varchar(255),       -- 档口名称
  wx numeric(19,4),               -- 微信支付金额
  wx_order integer,               -- 微信支付订单数量
  zfb numeric(19,4),              -- 支付宝支付金额
  zf_order integer,               -- 支付宝支付订单数量
  rmb numeric(19,4),              -- 现金支付金额
  rmb_order integer,              -- 现金支付订单数量
  xs numeric(19,4),               -- 行吧支付金额
  xs_order integer,               -- 行吧支付订单数量
  jd numeric(19,4),               -- 金豆支付金额
  jd_order integer,               -- 金豆支付订单数量
  order_sum integer,              -- 订单总数
  pay_sum numeric(19,4),          -- 支付总金额
  source_type integer,            -- 数据来源类型ID
  primary key (id)
);
```

### 6.3 输出格式关键特征

#### 6.3.1 DDL格式特征

- **中文表头注释**: 包含表中文名和业务描述
- **字段注释**: 每个字段都有中文注释说明
- **枚举标识**: 对于枚举字段，在注释中明确标出可选值
- **外键关系**: 明确标出外键关联关系
- **业务标识**: 特殊业务字段（如编码、ID）有详细说明

#### 6.3.2 MD格式特征

- **表级描述**: 详细的表业务用途说明
- **字段示例值**: 每个字段都提供真实的示例数据
- **枚举值详解**: 枚举字段的所有可能取值完整列出
- **补充说明**: 重要字段的额外业务逻辑说明
- **关联关系**: 与其他表的关联关系说明



## 7. 配置文件完整实现

### 7.1 配置文件 (`config.py`)

```python
import os
import sys

# 导入app_config获取数据库等配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import app_config
except ImportError:
    app_config = None

# Schema Tools专用配置
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "default_db_connection": None,  # 从命令行指定
    "default_business_context": "数据库管理系统", 
    "output_directory": "training/generated_data",
    
    # 处理链配置
    "default_pipeline": "full",
    "available_pipelines": {
        "full": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator", 
            "ddl_generator", 
            "doc_generator"
        ],
        "ddl_only": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator", 
            "ddl_generator"
        ],
        "analysis_only": [
            "database_inspector", 
            "data_sampler", 
            "comment_generator"
        ]
    },
    
    # 数据处理配置
    "sample_data_limit": 20,                    # 用于LLM分析的采样数据量
    "enum_detection_sample_limit": 5000,        # 枚举检测时的采样限制
    "enum_max_distinct_values": 20,             # 枚举字段最大不同值数量
    "enum_varchar_keywords": [                  # VARCHAR枚举关键词
        "性别", "gender", "状态", "status", "类型", "type", 
        "级别", "level", "方向", "direction", "品类", "classify",
        "模式", "mode", "格式", "format"
    ],
    "large_table_threshold": 1000000,           # 大表阈值（行数）
    
    # 并发配置
    "max_concurrent_tables": 3,                 # 最大并发处理表数
    
    # LLM配置
    "use_app_config_llm": True,                # 是否使用app_config中的LLM配置
    "comment_generation_timeout": 30,          # LLM调用超时时间(秒)
    "max_llm_retries": 3,                      # LLM调用最大重试次数
    
    # 系统表过滤配置
    "filter_system_tables": True,              # 是否过滤系统表
    "custom_system_prefixes": [],              # 用户自定义系统表前缀
    "custom_system_schemas": [],               # 用户自定义系统schema
    
    # 权限与安全配置
    "check_permissions": True,                 # 是否检查数据库权限
    "require_select_permission": True,         # 是否要求SELECT权限
    "allow_readonly_database": True,           # 是否允许只读数据库
    
    # 错误处理配置
    "continue_on_error": True,                 # 遇到错误是否继续
    "max_table_failures": 5,                  # 最大允许失败表数
    "skip_large_tables": False,               # 是否跳过超大表
    "max_table_size": 10000000,               # 最大表行数限制
    
    # 文件配置
    "ddl_file_suffix": ".ddl",
    "doc_file_suffix": "_detail.md",
    "log_file": "schema_tools.log",
    "create_subdirectories": True,            # 是否创建ddl/docs子目录
    
    # 输出格式配置
    "include_sample_data_in_comments": True,  # 注释中是否包含示例数据
    "max_comment_length": 500,                # 最大注释长度
    "include_field_statistics": True,         # 是否包含字段统计信息
    
    # 调试配置
    "debug_mode": False,                      # 调试模式
    "save_llm_prompts": False,               # 是否保存LLM提示词
    "save_llm_responses": False,             # 是否保存LLM响应
}

# 从app_config获取相关配置（如果可用）
if app_config:
    # 继承数据库配置
    if hasattr(app_config, 'PGVECTOR_CONFIG'):
        pgvector_config = app_config.PGVECTOR_CONFIG
        if not SCHEMA_TOOLS_CONFIG["default_db_connection"]:
            SCHEMA_TOOLS_CONFIG["default_db_connection"] = (
                f"postgresql://{pgvector_config['user']}:{pgvector_config['password']}"
                f"@{pgvector_config['host']}:{pgvector_config['port']}/{pgvector_config['dbname']}"
            )

def get_config():
    """获取当前配置"""
    return SCHEMA_TOOLS_CONFIG

def update_config(**kwargs):
    """更新配置"""
    SCHEMA_TOOLS_CONFIG.update(kwargs)

def validate_config():
    """验证配置有效性"""
    errors = []
    
    # 检查必要配置
    if SCHEMA_TOOLS_CONFIG["max_concurrent_tables"] <= 0:
        errors.append("max_concurrent_tables 必须大于0")
    
    if SCHEMA_TOOLS_CONFIG["sample_data_limit"] <= 0:
        errors.append("sample_data_limit 必须大于0")
    
    # 检查处理链配置
    default_pipeline = SCHEMA_TOOLS_CONFIG["default_pipeline"]
    available_pipelines = SCHEMA_TOOLS_CONFIG["available_pipelines"]
    
    if default_pipeline not in available_pipelines:
        errors.append(f"default_pipeline '{default_pipeline}' 不在 available_pipelines 中")
    
    if errors:
        raise ValueError("配置验证失败:\n" + "\n".join(f"  - {error}" for error in errors))
    
    return True

# 启动时验证配置
try:
    validate_config()
except ValueError as e:
    print(f"警告: {e}")
```

这个详细设计文档涵盖了Schema Tools的完整实现，包括：

## 核心特性

1. **完整的数据结构设计** - 标准化的数据模型
2. **工具注册机制** - 装饰器注册和自动依赖注入
3. **Pipeline处理链** - 可配置的处理流程
4. **并发处理** - 表级并发和错误处理
5. **LLM集成** - 智能注释生成和枚举检测
6. **权限管理** - 数据库权限检查和只读适配
7. **命令行接口** - 完整的CLI支持

## 实现亮点

- **类型安全**: 使用dataclass定义明确的数据结构
- **错误处理**: 完善的异常处理和重试机制
- **可扩展性**: 工具注册机制便于添加新功能
- **配置灵活**: 多层次配置支持
- **日志完整**: 详细的执行日志和统计报告