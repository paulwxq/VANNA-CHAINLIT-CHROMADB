import asyncio
import json
import logging
from typing import List, Dict, Any

from schema_tools.config import SCHEMA_TOOLS_CONFIG


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
        self.logger = logging.getLogger("schema_tools.ThemeExtractor")
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
3. 你需要自行决定每个主题应该涉及哪些表
4. 主题应该体现实际业务场景的数据分析需求
5. 考虑时间维度、对比分析、排名统计等多种分析角度
6. 为每个主题提供3-5个关键词，用于快速了解主题内容

请以JSON格式输出：
```json
{{
  "themes": [
    {{
      "topic_name": "日营业数据分析",
      "description": "基于 bss_business_day_data 表，分析每个服务区和档口每天的营业收入、订单数量、支付方式等",
      "related_tables": ["bss_business_day_data", "bss_branch", "bss_service_area"],
      "keywords": ["收入", "订单", "支付方式", "日报表"],
      "focus_areas": ["收入趋势", "服务区对比", "支付方式分布"]
    }}
  ]
}}
```

请确保：
- topic_name 简洁明了（10字以内）
- description 详细说明分析目标和价值（50字左右）
- related_tables 列出该主题需要用到的表名（数组格式）
- keywords 提供3-5个核心关键词（数组格式）
- focus_areas 列出3-5个具体的分析角度（保留用于生成问题）"""
        
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
                    
                    # 确保keywords存在且是数组
                    if 'keywords' not in theme:
                        # 从description中提取关键词
                        theme['keywords'] = self._extract_keywords_from_description(theme['description'])
                    elif isinstance(theme['keywords'], str):
                        theme['keywords'] = [theme['keywords']]
                    
                    # 保留focus_areas用于问题生成（如果没有则使用keywords）
                    if 'focus_areas' not in theme:
                        theme['focus_areas'] = theme['keywords'][:3]
                    
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
    
    def _extract_keywords_from_description(self, description: str) -> List[str]:
        """从描述中提取关键词（简单实现）"""
        # 定义常见的业务关键词
        business_keywords = [
            "收入", "营业额", "订单", "支付", "统计", "分析", "趋势", "对比",
            "排名", "汇总", "明细", "报表", "月度", "日度", "年度", "服务区",
            "档口", "商品", "客流", "车流", "效率", "占比", "增长"
        ]
        
        # 从描述中查找出现的关键词
        found_keywords = []
        for keyword in business_keywords:
            if keyword in description:
                found_keywords.append(keyword)
        
        # 如果找到的太少，返回默认值
        if len(found_keywords) < 3:
            found_keywords = ["数据分析", "统计报表", "业务查询"]
        
        return found_keywords[:5]  # 最多返回5个 