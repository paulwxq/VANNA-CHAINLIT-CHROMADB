import asyncio
from typing import List, Dict, Any, Tuple
from data_pipeline.tools.base import BaseTool, ToolRegistry
from data_pipeline.utils.data_structures import ProcessingResult, TableProcessingContext, FieldInfo

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
```

注释生成要求:
1. 如果原注释是英文，翻译为中文并改进
2. 根据字段名、类型和样例值推断字段含义
3. 识别可能的枚举字段（如状态、类型、级别等）
4. 枚举判断标准: VARCHAR类型 + 样例值重复度高 + 字段名暗示分类
5. 注释要贴近{business_context}的业务场景

请输出JSON格式的分析结果:"""
        
        return prompt
    
    async def _call_llm_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """带重试的LLM调用"""
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        
        for attempt in range(max_retries):
            try:
                # 使用vanna实例的chat_with_llm方法进行自由聊天
                # 这是专门用于生成训练数据的方法，不会查询向量数据库
                response = await asyncio.to_thread(
                    self.vn.chat_with_llm, 
                    question=prompt,
                    system_prompt="你是一个专业的数据库文档专家，专门负责生成高质量的中文数据库表和字段注释。"
                )
                
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
        from data_pipeline.tools.database_inspector import DatabaseInspectorTool
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        
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