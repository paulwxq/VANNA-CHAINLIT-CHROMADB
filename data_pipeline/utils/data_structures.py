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
    db_connection: Optional[str] = None  # 数据库连接字符串
    current_step: str = "initialized"
    step_results: Dict[str, ProcessingResult] = field(default_factory=dict)
    start_time: Optional[float] = None
    
    def update_step(self, step_name: str, result: ProcessingResult):
        """更新步骤结果"""
        self.current_step = step_name
        self.step_results[step_name] = result