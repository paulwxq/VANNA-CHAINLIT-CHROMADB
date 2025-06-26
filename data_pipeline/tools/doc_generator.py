import os
from typing import List, Dict, Any
from data_pipeline.tools.base import BaseTool, ToolRegistry
from data_pipeline.utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo, TableMetadata
from data_pipeline.config import SCHEMA_TOOLS_CONFIG

@ToolRegistry.register("doc_generator")
class DocGeneratorTool(BaseTool):
    """MD文档生成工具"""
    
    needs_llm = False
    tool_name = "文档生成器"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def execute(self, context: TableProcessingContext) -> ProcessingResult:
        """执行MD文档生成"""
        try:
            table_metadata = context.table_metadata
            
            # 获取DDL生成结果（如果有）
            ddl_result = context.step_results.get('ddl_generator')
            ddl_content = ddl_result.data.get('ddl_content', '') if ddl_result and ddl_result.success else ''
            
            # 生成MD内容
            md_content = self._generate_md_content(table_metadata, ddl_content)
            
            # 确定文件名和路径
            filename = context.file_manager.get_safe_filename(
                table_metadata.schema_name,
                table_metadata.table_name,
                SCHEMA_TOOLS_CONFIG["doc_file_suffix"]
            )
            
            # 确定子目录
            subdirectory = "docs" if SCHEMA_TOOLS_CONFIG["create_subdirectories"] else None
            filepath = context.file_manager.get_full_path(filename, subdirectory)
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            self.logger.info(f"MD文档已生成: {filepath}")
            
            return ProcessingResult(
                success=True,
                data={
                    'filename': filename,
                    'filepath': filepath,
                    'content_length': len(md_content)
                },
                metadata={'tool': self.tool_name}
            )
            
        except Exception as e:
            self.logger.exception(f"MD文档生成失败")
            return ProcessingResult(
                success=False,
                error_message=f"MD文档生成失败: {str(e)}"
            )
    
    def _generate_md_content(self, table_metadata: TableMetadata, ddl_content: str) -> str:
        """生成MD文档内容"""
        lines = []
        
        # 标题 - 只显示表名，不加解释和字数统计
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
            lines.append(f"## {table_metadata.table_name}（{table_name_part}）")
            # 表描述
            lines.append(f"{table_metadata.table_name} 表{comment}")
        else:
            lines.append(f"## {table_metadata.table_name}（数据表）")
            lines.append(f"{table_metadata.table_name} 表")
        
        # 字段列表（去掉前面的空行）
        lines.append("字段列表：")
        for field in table_metadata.fields:
            field_line = self._generate_field_line(field, table_metadata)
            lines.append(field_line)
        
        # 字段补充说明（去掉前面的空行）
        supplementary_info = self._generate_supplementary_info(table_metadata)
        if supplementary_info:
            lines.append("字段补充说明：")
            lines.extend(supplementary_info)
        
        # DDL语句（可选）
        if ddl_content and SCHEMA_TOOLS_CONFIG.get("include_ddl_in_doc", False):
            lines.append("### DDL语句")
            lines.append("```sql")
            lines.append(ddl_content)
            lines.append("```")
            lines.append("")
        
        # 删除表统计信息部分
        
        return '\n'.join(lines)
    
    def _generate_field_line(self, field: FieldInfo, table_metadata: TableMetadata) -> str:
        """生成字段说明行"""
        # 基础信息
        parts = [f"- {field.name}"]
        
        # 类型信息
        type_info = self._format_field_type_for_doc(field)
        parts.append(f"({type_info})")
        
        # 注释
        if field.comment:
            parts.append(f"- {field.comment}")
        
        # 约束信息
        constraints = []
        if field.is_primary_key:
            constraints.append("主键")
        if field.is_foreign_key:
            constraints.append("外键")
        if not field.nullable:
            constraints.append("非空")
        
        if constraints:
            parts.append(f"[{', '.join(constraints)}]")
        
        # 示例值（枚举类型显示更多，其他类型只显示2个）
        sample_values = self._get_field_sample_values(field.name, table_metadata)
        if sample_values:
            if field.is_enum:
                # 枚举类型最多显示10个
                display_values = sample_values[:10]
            else:
                # 其他类型只显示2个
                display_values = sample_values[:2]
            sample_str = f"[示例: {', '.join(display_values)}]"
            parts.append(sample_str)
        
        return ' '.join(parts)
    
    def _format_field_type_for_doc(self, field: FieldInfo) -> str:
        """为文档格式化字段类型"""
        if field.type.lower() in ['character varying', 'varchar'] and field.max_length:
            return f"varchar({field.max_length})"
        elif field.type.lower() == 'numeric' and field.precision:
            if field.scale:
                return f"numeric({field.precision},{field.scale})"
            else:
                return f"numeric({field.precision})"
        elif 'timestamp' in field.type.lower():
            if '(' in field.type:
                # 提取精度
                precision = field.type.split('(')[1].split(')')[0]
                return f"timestamp({precision})"
            return "timestamp"
        else:
            return field.type
    
    def _get_field_sample_values(self, field_name: str, table_metadata: TableMetadata) -> List[str]:
        """获取字段的示例值"""
        sample_values = []
        seen_values = set()
        
        for sample in table_metadata.sample_data:
            if field_name in sample:
                value = sample[field_name]
                if value is not None:
                    str_value = str(value)
                    if str_value not in seen_values:
                        seen_values.add(str_value)
                        sample_values.append(str_value)
                        if len(sample_values) >= 3:
                            break
        
        return sample_values
    
    def _generate_supplementary_info(self, table_metadata: TableMetadata) -> List[str]:
        """生成字段补充说明"""
        info_lines = []
        
        # 主键信息
        primary_keys = [f.name for f in table_metadata.fields if f.is_primary_key]
        if primary_keys:
            if len(primary_keys) == 1:
                info_lines.append(f"- {primary_keys[0]} 为主键")
            else:
                info_lines.append(f"- 复合主键：{', '.join(primary_keys)}")
        
        # 外键信息
        foreign_keys = [(f.name, f.comment) for f in table_metadata.fields if f.is_foreign_key]
        for fk_name, fk_comment in foreign_keys:
            if fk_comment and '关联' in fk_comment:
                info_lines.append(f"- {fk_name} {fk_comment}")
            else:
                info_lines.append(f"- {fk_name} 为外键")
        
        # 枚举字段信息（包括逻辑枚举类型）
        enum_fields = [f for f in table_metadata.fields if f.is_enum and f.enum_values]
        for field in enum_fields:
            values_str = '、'.join(field.enum_values)
            # 不显示取值数量，因为可能不完整
            info_lines.append(f"- {field.name} 为枚举字段，包含取值：{values_str}")
            # 不显示enum_description，因为它通常是重复的描述
        
        # 检查逻辑枚举（字段名暗示但未被识别为枚举的字段）
        logical_enum_keywords = ["状态", "类型", "级别", "方向", "品类", "模式", "格式", "性别"]
        for field in table_metadata.fields:
            if not field.is_enum:  # 只检查未被识别为枚举的字段
                field_name_lower = field.name.lower()
                if any(keyword in field_name_lower for keyword in logical_enum_keywords):
                    # 获取该字段的示例值来判断是否可能是逻辑枚举
                    sample_values = self._get_field_sample_values(field.name, table_metadata)
                    if sample_values and len(sample_values) <= 10:  # 如果样例值数量较少，可能是逻辑枚举
                        values_str = '、'.join(sample_values[:10])
                        info_lines.append(f"- {field.name} 疑似枚举字段，当前取值：{values_str}")
        
        # 特殊字段说明
        for field in table_metadata.fields:
            # UUID字段
            if field.type.lower() == 'uuid':
                info_lines.append(f"- {field.name} 使用 UUID 编码")
            
            # 时间戳字段
            elif 'timestamp' in field.type.lower() and field.default_value:
                if 'now()' in field.default_value.lower() or 'current_timestamp' in field.default_value.lower():
                    info_lines.append(f"- {field.name} 自动记录当前时间")
            
            # JSON字段
            elif field.type.lower() in ['json', 'jsonb']:
                info_lines.append(f"- {field.name} 存储JSON格式数据")
        
        # 表关联说明
        if table_metadata.table_name.endswith('_rel') or table_metadata.table_name.endswith('_relation'):
            info_lines.append(f"- 本表是关联表，用于多对多关系映射")
        
        return info_lines
    
    def _generate_statistics_info(self, table_metadata: TableMetadata) -> List[str]:
        """生成表统计信息"""
        stats_lines = []
        
        if table_metadata.row_count is not None:
            stats_lines.append(f"- 数据行数：{table_metadata.row_count:,}")
        
        if table_metadata.table_size:
            stats_lines.append(f"- 表大小：{table_metadata.table_size}")
        
        # 字段统计
        total_fields = len(table_metadata.fields)
        nullable_fields = sum(1 for f in table_metadata.fields if f.nullable)
        enum_fields = sum(1 for f in table_metadata.fields if f.is_enum)
        
        stats_lines.append(f"- 字段总数：{total_fields}")
        if nullable_fields > 0:
            stats_lines.append(f"- 可空字段：{nullable_fields}")
        if enum_fields > 0:
            stats_lines.append(f"- 枚举字段：{enum_fields}")
        
        return stats_lines