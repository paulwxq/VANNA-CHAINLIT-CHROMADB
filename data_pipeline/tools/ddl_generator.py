import os
from typing import List, Dict, Any
from data_pipeline.tools.base import BaseTool, ToolRegistry
from data_pipeline.utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo, TableMetadata
from data_pipeline.config import SCHEMA_TOOLS_CONFIG

@ToolRegistry.register("ddl_generator")
class DDLGeneratorTool(BaseTool):
    """DDL格式生成工具"""
    
    needs_llm = False
    tool_name = "DDL生成器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行DDL生成"""
        try:
            table_metadata = context.table_metadata
            
            # 生成DDL内容
            ddl_content = self._generate_ddl_content(table_metadata)
            
            # 如果有file_manager，则写入文件（正常的data_pipeline流程）
            if context.file_manager:
                # 确定文件名和路径
                filename = context.file_manager.get_safe_filename(
                    table_metadata.schema_name,
                    table_metadata.table_name,
                    SCHEMA_TOOLS_CONFIG["ddl_file_suffix"]
                )
                
                # 确定子目录
                subdirectory = "ddl" if SCHEMA_TOOLS_CONFIG["create_subdirectories"] else None
                filepath = context.file_manager.get_full_path(filename, subdirectory)
                
                # 写入文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(ddl_content)
                
                self.logger.info(f"DDL文件已生成: {filepath}")
                
                return ProcessingResult(
                    success=True,
                    data={
                        'filename': filename,
                        'filepath': filepath,
                        'content_length': len(ddl_content),
                        'ddl_content': ddl_content  # 保存内容供后续工具使用
                    },
                    metadata={'tool': self.tool_name}
                )
            else:
                # 如果没有file_manager，只返回DDL内容（API调用场景）
                self.logger.info("DDL内容已生成（API调用模式，不写入文件）")
                
                return ProcessingResult(
                    success=True,
                    data={
                        'filename': f"{table_metadata.schema_name}_{table_metadata.table_name}.ddl",
                        'filepath': None,  # 不写入文件
                        'content_length': len(ddl_content),
                        'ddl_content': ddl_content  # 保存内容供后续工具使用
                    },
                    metadata={'tool': self.tool_name}
                )
            
        except Exception as e:
            self.logger.exception(f"DDL生成失败")
            return ProcessingResult(
                success=False,
                error_message=f"DDL生成失败: {str(e)}"
            )
    
    def _generate_ddl_content(self, table_metadata: TableMetadata) -> str:
        """生成DDL内容"""
        lines = []
        
        # 表头注释 - 只显示表名，不加解释和字数统计
        if table_metadata.comment:
            # 提取表名部分（去掉解释和字数统计）
            comment = table_metadata.comment
            # 去掉可能的字数统计 (XX字)
            import re
            comment = re.sub(r'[（(]\d+字[）)]', '', comment)
            # 只取第一句话或逗号前的部分
            if '，' in comment:
                table_name_part = comment.split('，')[0]
            elif '。' in comment:
                table_name_part = comment.split('。')[0]
            else:
                table_name_part = comment.strip()
            lines.append(f"-- 中文名: {table_name_part}")
            lines.append(f"-- 描述: {comment}")
        else:
            lines.append(f"-- 中文名: {table_metadata.table_name}")
        
        # CREATE TABLE语句
        lines.append(f"create table {table_metadata.full_name} (")
        
        # 字段定义
        field_lines = []
        for field in table_metadata.fields:
            field_line = self._generate_field_line(field)
            field_lines.append(field_line)
        
        # 主键定义
        primary_keys = [f.name for f in table_metadata.fields if f.is_primary_key]
        if primary_keys:
            field_lines.append(f"  primary key ({', '.join(primary_keys)})")
        
        # 组合字段行
        lines.extend([line if i == len(field_lines) - 1 else line + ","
                     for i, line in enumerate(field_lines)])
        
        lines.append(");")
        
        return '\n'.join(lines)
    
    def _generate_field_line(self, field: FieldInfo) -> str:
        """生成字段定义行"""
        parts = [f"  {field.name}"]
        
        # 字段类型
        field_type = self._format_field_type(field)
        parts.append(field_type)
        
        # NOT NULL约束
        if not field.nullable:
            parts.append("not null")
        
        # 默认值
        if field.default_value and not self._should_skip_default(field.default_value):
            parts.append(f"default {self._format_default_value(field.default_value)}")
        
        # 组合字段定义
        field_def = ' '.join(parts)
        
        # 添加注释
        comment = self._format_field_comment(field)
        if comment:
            # 计算对齐空格（减少到30个字符对齐）
            padding = max(1, 30 - len(field_def))
            field_line = f"{field_def}{' ' * padding}-- {comment}"
        else:
            field_line = field_def
        
        return field_line
    
    def _format_field_type(self, field: FieldInfo) -> str:
        """格式化字段类型"""
        field_type = field.type.lower()
        
        # 处理带长度的类型
        if field_type in ['character varying', 'varchar'] and field.max_length:
            return f"varchar({field.max_length})"
        elif field_type == 'character' and field.max_length:
            return f"char({field.max_length})"
        elif field_type == 'numeric' and field.precision:
            if field.scale:
                return f"numeric({field.precision},{field.scale})"
            else:
                return f"numeric({field.precision})"
        elif field_type == 'timestamp without time zone':
            return "timestamp"
        elif field_type == 'timestamp with time zone':
            return "timestamptz"
        elif field_type in ['integer', 'int']:
            return "integer"
        elif field_type in ['bigint', 'int8']:
            return "bigint"
        elif field_type in ['smallint', 'int2']:
            return "smallint"
        elif field_type in ['double precision', 'float8']:
            return "double precision"
        elif field_type in ['real', 'float4']:
            return "real"
        elif field_type == 'boolean':
            return "boolean"
        elif field_type == 'text':
            return "text"
        elif field_type == 'date':
            return "date"
        elif field_type == 'time without time zone':
            return "time"
        elif field_type == 'time with time zone':
            return "timetz"
        elif field_type == 'json':
            return "json"
        elif field_type == 'jsonb':
            return "jsonb"
        elif field_type == 'uuid':
            return "uuid"
        elif field_type.startswith('timestamp(') and 'without time zone' in field_type:
            # 处理 timestamp(3) without time zone
            precision = field_type.split('(')[1].split(')')[0]
            return f"timestamp({precision})"
        else:
            return field_type
    
    def _format_default_value(self, default_value: str) -> str:
        """格式化默认值"""
        # 移除可能的类型转换
        if '::' in default_value:
            default_value = default_value.split('::')[0]
        
        # 处理函数调用
        if default_value.lower() in ['now()', 'current_timestamp']:
            return 'current_timestamp'
        elif default_value.lower() == 'current_date':
            return 'current_date'
        
        # 处理字符串值
        if not (default_value.startswith("'") and default_value.endswith("'")):
            # 检查是否为数字或布尔值
            if default_value.lower() in ['true', 'false']:
                return default_value.lower()
            elif default_value.replace('.', '').replace('-', '').isdigit():
                return default_value
            else:
                # 其他情况加引号
                return f"'{default_value}'"
        
        return default_value
    
    def _should_skip_default(self, default_value: str) -> bool:
        """判断是否应跳过默认值"""
        # 跳过序列默认值
        if 'nextval(' in default_value.lower():
            return True
        
        # 跳过空字符串
        if default_value.strip() in ['', "''", '""']:
            return True
        
        return False
    
    def _format_field_comment(self, field: FieldInfo) -> str:
        """格式化字段注释"""
        comment_parts = []
        
        # 基础注释
        if field.comment:
            comment_parts.append(field.comment)
        
        # 主键标识
        if field.is_primary_key:
            comment_parts.append("主键")
        
        # 外键标识
        if field.is_foreign_key:
            comment_parts.append("外键")
        
        # 去掉小括号，直接返回注释内容
        return '，'.join(comment_parts) if comment_parts else ""