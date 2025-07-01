import asyncio
import json
from typing import List, Dict, Any

from data_pipeline.config import SCHEMA_TOOLS_CONFIG
import logging


class ThemeExtractor:
    """主题提取器"""
    
    def __init__(self, vn, business_context: str):
        """
        初始化主题提取器
        
        Args:
            vn: vanna实例
            business_context: 业务上下文
        """
        self.vn = vn
        self.business_context = business_context
        self.logger = logging.getLogger("ThemeExtractor")
        self.config = SCHEMA_TOOLS_CONFIG
        
    async def extract_themes(self, md_contents: str) -> List[Dict[str, Any]]:
        """
        从MD内容中提取分析主题
        
        Args:
            md_contents: 所有MD文件的组合内容
            
        Returns:
            主题列表
        """
        theme_count = self.config['qs_generation']['theme_count']
        
        prompt = self._build_theme_extraction_prompt(md_contents, theme_count)
        
        try:
            # 调用LLM提取主题
            response = await self._call_llm(prompt)
            
            # 解析响应
            themes = self._parse_theme_response(response)
            
            self.logger.info(f"成功提取 {len(themes)} 个分析主题")
            
            return themes
            
        except Exception as e:
            self.logger.error(f"主题提取失败: {e}")
            raise
    
    def _build_theme_extraction_prompt(self, md_contents: str, theme_count: int) -> str:
        """构建主题提取的prompt"""
        prompt = f"""你是一位经验丰富的业务数据分析师，正在分析{self.business_context}的数据库。

以下是数据库中所有表的详细结构说明：

{md_contents}

基于对这些表结构的理解，请从业务分析的角度提出 {theme_count} 个数据查询分析主题。

要求：
1. 每个主题应该有明确的业务价值和分析目标
2. 主题之间应该有所区别，覆盖不同的业务领域  
3. 你需要自行决定每个主题应该涉及哪些表（使用实际存在的表名）
4. 主题应该体现实际业务场景的数据分析需求
5. 考虑时间维度、对比分析、排名统计等多种分析角度
6. 在选择业务实体时，请忽略以下技术性字段：
   - id、主键ID等标识字段
   - create_time、created_at、create_ts等创建时间字段
   - update_time、updated_at、update_ts等更新时间字段
   - delete_time、deleted_at、delete_ts等删除时间字段
   - version、版本号等版本控制字段
   - created_by、updated_by、deleted_by等操作人字段
7. 重点关注具有业务含义的实体字段和指标

请以JSON格式输出：
```json
{{
  "themes": [
    {{
      "topic_name": "日营业数据分析",
      "description": "基于 bss_business_day_data 表，分析每个服务区和档口每天的营业收入、订单数量、支付方式等",
      "related_tables": ["bss_business_day_data", "bss_branch", "bss_service_area"],
      "biz_entities": ["服务区", "档口", "支付方式", "营收"],
      "biz_metrics": ["收入趋势", "服务区对比", "支付方式分布"]
    }}
  ]
}}
```

请确保：
- topic_name 简洁明了（10字以内）
- description 详细说明分析目标和价值（50字左右）
- related_tables 列出该主题需要用到的表名（数组格式）
- biz_entities 列出3-5个主要业务实体（表的维度字段或非数值型字段，如服务区、公司、车辆等）
- biz_metrics 列出3-5个主要业务指标名称（统计指标，如收入趋势、对比分析等）"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        try:
            # 使用vanna的chat_with_llm方法
            response = await asyncio.to_thread(
                self.vn.chat_with_llm,
                question=prompt,
                system_prompt="你是一个专业的数据分析师，擅长从业务角度设计数据分析主题和查询方案。请严格按照要求的JSON格式输出。"
            )
            
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            return response.strip()
            
        except Exception as e:
            self.logger.error(f"LLM调用失败: {e}")
            raise
    
    def _parse_theme_response(self, response: str) -> List[Dict[str, Any]]:
        """解析LLM的主题响应"""
        try:
            # 提取JSON部分
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = response
            
            # 解析JSON
            data = json.loads(json_str)
            themes = data.get('themes', [])
            
            # 验证和标准化主题格式
            validated_themes = []
            for theme in themes:
                # 兼容旧格式（name -> topic_name）
                if 'name' in theme and 'topic_name' not in theme:
                    theme['topic_name'] = theme['name']
                
                # 验证必需字段
                required_fields = ['topic_name', 'description', 'related_tables']
                if all(key in theme for key in required_fields):
                    # 确保related_tables是数组
                    if isinstance(theme['related_tables'], str):
                        theme['related_tables'] = [theme['related_tables']]
                    
                    # 确保biz_entities存在且是数组
                    if 'biz_entities' not in theme:
                        # 从description中提取业务实体
                        theme['biz_entities'] = self._extract_biz_entities_from_description(theme['description'])
                    elif isinstance(theme['biz_entities'], str):
                        theme['biz_entities'] = [theme['biz_entities']]
                    
                    # 确保biz_metrics存在且是数组
                    if 'biz_metrics' not in theme:
                        # 从description中提取业务指标
                        theme['biz_metrics'] = self._extract_biz_metrics_from_description(theme['description'])
                    elif isinstance(theme['biz_metrics'], str):
                        theme['biz_metrics'] = [theme['biz_metrics']]
                    
                    validated_themes.append(theme)
                else:
                    self.logger.warning(f"主题格式不完整，跳过: {theme.get('topic_name', 'Unknown')}")
            
            return validated_themes
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}")
            self.logger.debug(f"原始响应: {response}")
            raise ValueError(f"无法解析LLM响应为JSON格式: {e}")
        except Exception as e:
            self.logger.error(f"解析主题响应失败: {e}")
            raise
    
    def _extract_biz_entities_from_description(self, description: str) -> List[str]:
        """从描述中提取业务实体（简单实现）"""
        # 定义常见的业务实体关键词
        entity_keywords = [
            "服务区", "档口", "商品", "公司", "分公司", "车辆", "支付方式",
            "订单", "客户", "营收", "路段", "区域", "品牌", "品类"
        ]
        
        # 从描述中查找出现的实体关键词
        found_entities = []
        for entity in entity_keywords:
            if entity in description:
                found_entities.append(entity)
        
        # 如果找到的太少，返回默认值
        if len(found_entities) < 3:
            found_entities = ["业务实体", "数据对象", "分析主体"]
        
        return found_entities[:5]  # 最多返回5个
    
    def _extract_biz_metrics_from_description(self, description: str) -> List[str]:
        """从描述中提取业务指标（简单实现）"""
        # 定义常见的业务指标关键词
        metrics_keywords = [
            "收入趋势", "营业额对比", "支付方式分布", "服务区对比", "增长率",
            "占比分析", "排名统计", "效率评估", "流量分析", "转化率"
        ]
        
        # 从描述中查找出现的指标关键词
        found_metrics = []
        for metric in metrics_keywords:
            if any(word in description for word in metric.split()):
                found_metrics.append(metric)
        
        # 如果找到的太少，返回默认值
        if len(found_metrics) < 3:
            found_metrics = ["数据统计", "趋势分析", "对比分析"]
        
        return found_metrics[:5]  # 最多返回5个 