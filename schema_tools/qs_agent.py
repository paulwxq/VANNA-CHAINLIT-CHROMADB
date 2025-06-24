import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from schema_tools.config import SCHEMA_TOOLS_CONFIG
from schema_tools.validators import FileCountValidator
from schema_tools.analyzers import MDFileAnalyzer, ThemeExtractor
from schema_tools.utils.logger import setup_logging
from core.vanna_llm_factory import create_vanna_instance


class QuestionSQLGenerationAgent:
    """Question-SQL生成Agent"""
    
    def __init__(self, 
                 output_dir: str,
                 table_list_file: str,
                 business_context: str,
                 db_name: str = None):
        """
        初始化Agent
        
        Args:
            output_dir: 输出目录（包含DDL和MD文件）
            table_list_file: 表清单文件路径
            business_context: 业务上下文
            db_name: 数据库名称（用于输出文件命名）
        """
        self.output_dir = Path(output_dir)
        self.table_list_file = table_list_file
        self.business_context = business_context
        self.db_name = db_name or "db"
        
        self.config = SCHEMA_TOOLS_CONFIG
        self.logger = logging.getLogger("schema_tools.QSAgent")
        
        # 初始化组件
        self.validator = FileCountValidator()
        self.md_analyzer = MDFileAnalyzer(output_dir)
        
        # vanna实例和主题提取器将在需要时初始化
        self.vn = None
        self.theme_extractor = None
        
        # 中间结果存储
        self.intermediate_results = []
        self.intermediate_file = None
        
    async def generate(self) -> Dict[str, Any]:
        """
        生成Question-SQL对
        
        Returns:
            生成结果报告
        """
        start_time = time.time()
        
        try:
            self.logger.info("🚀 开始生成Question-SQL训练数据")
            
            # 1. 验证文件数量
            self.logger.info("📋 验证文件数量...")
            validation_result = self.validator.validate(self.table_list_file, str(self.output_dir))
            
            if not validation_result.is_valid:
                self.logger.error(f"❌ 文件验证失败: {validation_result.error}")
                if validation_result.missing_ddl:
                    self.logger.error(f"缺失DDL文件: {validation_result.missing_ddl}")
                if validation_result.missing_md:
                    self.logger.error(f"缺失MD文件: {validation_result.missing_md}")
                raise ValueError(f"文件验证失败: {validation_result.error}")
            
            self.logger.info(f"✅ 文件验证通过: {validation_result.table_count}个表")
            
            # 2. 读取所有MD文件内容
            self.logger.info("📖 读取MD文件...")
            md_contents = await self.md_analyzer.read_all_md_files()
            
            # 3. 初始化LLM相关组件
            self._initialize_llm_components()
            
            # 4. 提取分析主题
            self.logger.info("🎯 提取分析主题...")
            themes = await self.theme_extractor.extract_themes(md_contents)
            self.logger.info(f"✅ 成功提取 {len(themes)} 个分析主题")
            
            for i, theme in enumerate(themes):
                topic_name = theme.get('topic_name', theme.get('name', ''))
                description = theme.get('description', '')
                self.logger.info(f"  {i+1}. {topic_name}: {description}")
            
            # 5. 初始化中间结果文件
            self._init_intermediate_file()
            
            # 6. 处理每个主题
            all_qs_pairs = []
            failed_themes = []
            
            # 根据配置决定是并行还是串行处理
            max_concurrent = self.config['qs_generation'].get('max_concurrent_themes', 1)
            if max_concurrent > 1:
                results = await self._process_themes_parallel(themes, md_contents, max_concurrent)
            else:
                results = await self._process_themes_serial(themes, md_contents)
            
            # 7. 整理结果
            for result in results:
                if result['success']:
                    all_qs_pairs.extend(result['qs_pairs'])
                else:
                    failed_themes.append(result['theme_name'])
            
            # 8. 保存最终结果
            output_file = await self._save_final_results(all_qs_pairs)
            
            # 8.5 生成metadata.txt文件
            await self._generate_metadata_file(themes)
            
            # 9. 清理中间文件
            if not failed_themes:  # 只有全部成功才清理
                self._cleanup_intermediate_file()
            
            # 10. 生成报告
            end_time = time.time()
            report = {
                'success': True,
                'total_themes': len(themes),
                'successful_themes': len(themes) - len(failed_themes),
                'failed_themes': failed_themes,
                'total_questions': len(all_qs_pairs),
                'output_file': str(output_file),
                'execution_time': end_time - start_time
            }
            
            self._print_summary(report)
            
            return report
            
        except Exception as e:
            self.logger.exception("❌ Question-SQL生成失败")
            
            # 保存当前已生成的结果
            if self.intermediate_results:
                recovery_file = self._save_intermediate_results()
                self.logger.warning(f"⚠️  中间结果已保存到: {recovery_file}")
            
            raise
    
    def _initialize_llm_components(self):
        """初始化LLM相关组件"""
        if not self.vn:
            self.logger.info("初始化LLM组件...")
            self.vn = create_vanna_instance()
            self.theme_extractor = ThemeExtractor(self.vn, self.business_context)
    
    async def _process_themes_serial(self, themes: List[Dict], md_contents: str) -> List[Dict]:
        """串行处理主题"""
        results = []
        
        for i, theme in enumerate(themes):
            self.logger.info(f"处理主题 {i+1}/{len(themes)}: {theme.get('topic_name', theme.get('name', ''))}")
            result = await self._process_single_theme(theme, md_contents)
            results.append(result)
            
            # 检查是否需要继续
            if not result['success'] and not self.config['qs_generation']['continue_on_theme_error']:
                self.logger.error(f"主题处理失败，停止处理")
                break
        
        return results
    
    async def _process_themes_parallel(self, themes: List[Dict], md_contents: str, max_concurrent: int) -> List[Dict]:
        """并行处理主题"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(theme):
            async with semaphore:
                return await self._process_single_theme(theme, md_contents)
        
        tasks = [process_with_semaphore(theme) for theme in themes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                theme_name = themes[i].get('topic_name', themes[i].get('name', ''))
                self.logger.error(f"主题 '{theme_name}' 处理异常: {result}")
                processed_results.append({
                    'success': False,
                    'theme_name': theme_name,
                    'error': str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _process_single_theme(self, theme: Dict, md_contents: str) -> Dict:
        """处理单个主题"""
        theme_name = theme.get('topic_name', theme.get('name', ''))
        
        try:
            self.logger.info(f"🔍 开始处理主题: {theme_name}")
            
            # 构建prompt
            prompt = self._build_qs_generation_prompt(theme, md_contents)
            
            # 调用LLM生成
            response = await self._call_llm(prompt)
            
            # 解析响应
            qs_pairs = self._parse_qs_response(response)
            
            # 验证和清理
            validated_pairs = self._validate_qs_pairs(qs_pairs, theme_name)
            
            # 保存中间结果
            await self._save_theme_results(theme_name, validated_pairs)
            
            self.logger.info(f"✅ 主题 '{theme_name}' 处理成功，生成 {len(validated_pairs)} 个问题")
            
            return {
                'success': True,
                'theme_name': theme_name,
                'qs_pairs': validated_pairs
            }
            
        except Exception as e:
            self.logger.error(f"❌ 处理主题 '{theme_name}' 失败: {e}")
            return {
                'success': False,
                'theme_name': theme_name,
                'error': str(e),
                'qs_pairs': []
            }
    
    def _build_qs_generation_prompt(self, theme: Dict, md_contents: str) -> str:
        """构建Question-SQL生成的prompt"""
        questions_count = self.config['qs_generation']['questions_per_theme']
        
        # 兼容新旧格式
        topic_name = theme.get('topic_name', theme.get('name', ''))
        description = theme.get('description', '')
        focus_areas = theme.get('focus_areas', theme.get('keywords', []))
        related_tables = theme.get('related_tables', [])
        
        prompt = f"""你是一位业务数据分析师，正在为{self.business_context}设计数据查询。

当前分析主题：{topic_name}
主题描述：{description}
关注领域：{', '.join(focus_areas)}
相关表：{', '.join(related_tables)}

数据库表结构信息：
{md_contents}

请为这个主题生成 {questions_count} 个业务问题和对应的SQL查询。

要求：
1. 问题应该从业务角度出发，贴合主题要求，具有实际分析价值
2. SQL必须使用PostgreSQL语法
3. 考虑实际业务逻辑（如软删除使用 delete_ts IS NULL 条件）
4. 使用中文别名提高可读性（使用 AS 指定列别名）
5. 问题应该多样化，覆盖不同的分析角度
6. 包含时间筛选、分组统计、排序、限制等不同类型的查询
7. SQL语句末尾必须以分号结束
8. **重要：问题和SQL都必须是单行文本，不能包含换行符**

输出JSON格式（注意SQL中的双引号需要转义）：
```json
[
  {{
    "question": "具体的业务问题？",
    "sql": "SELECT column AS 中文名 FROM table WHERE condition;"
  }}
]
```

生成的问题应该包括但不限于：
- 趋势分析（按时间维度）
- 对比分析（不同维度对比）
- 排名统计（TOP N）
- 汇总统计（总量、平均值等）
- 明细查询（特定条件的详细数据）"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        try:
            response = await asyncio.to_thread(
                self.vn.chat_with_llm,
                question=prompt,
                system_prompt="你是一个专业的数据分析师，精通PostgreSQL语法，擅长设计有业务价值的数据查询。请严格按照JSON格式输出。特别注意：生成的问题和SQL都必须是单行文本，不能包含换行符。"
            )
            
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            return response.strip()
            
        except Exception as e:
            self.logger.error(f"LLM调用失败: {e}")
            raise
    
    def _parse_qs_response(self, response: str) -> List[Dict[str, str]]:
        """解析Question-SQL响应"""
        try:
            # 提取JSON部分
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response
            
            # 解析JSON
            qs_pairs = json.loads(json_str)
            
            if not isinstance(qs_pairs, list):
                raise ValueError("响应不是列表格式")
            
            return qs_pairs
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}")
            self.logger.debug(f"原始响应: {response}")
            raise ValueError(f"无法解析LLM响应为JSON格式: {e}")
    
    def _validate_qs_pairs(self, qs_pairs: List[Dict], theme_name: str) -> List[Dict[str, str]]:
        """验证和清理Question-SQL对"""
        validated = []
        
        for i, pair in enumerate(qs_pairs):
            if not isinstance(pair, dict):
                self.logger.warning(f"跳过无效格式的项 {i+1}")
                continue
            
            question = pair.get('question', '').strip()
            sql = pair.get('sql', '').strip()
            
            if not question or not sql:
                self.logger.warning(f"跳过空问题或SQL的项 {i+1}")
                continue
            
            # 清理question中的换行符，替换为空格
            question = ' '.join(question.split())
            
            # 清理SQL中的换行符和多余空格，压缩为单行
            sql = ' '.join(sql.split())
            
            # 确保SQL以分号结束
            if not sql.endswith(';'):
                sql += ';'
            
            validated.append({
                'question': question,
                'sql': sql
            })
        
        self.logger.info(f"主题 '{theme_name}': 验证通过 {len(validated)}/{len(qs_pairs)} 个问题")
        
        return validated
    
    def _init_intermediate_file(self):
        """初始化中间结果文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.intermediate_file = self.output_dir / f"qs_intermediate_{timestamp}.json"
        self.intermediate_results = []
        self.logger.info(f"中间结果文件: {self.intermediate_file}")
    
    async def _save_theme_results(self, theme_name: str, qs_pairs: List[Dict]):
        """保存单个主题的结果"""
        theme_result = {
            "theme": theme_name,
            "timestamp": datetime.now().isoformat(),
            "questions_count": len(qs_pairs),
            "questions": qs_pairs
        }
        
        self.intermediate_results.append(theme_result)
        
        # 立即保存到中间文件
        if self.config['qs_generation']['save_intermediate']:
            try:
                with open(self.intermediate_file, 'w', encoding='utf-8') as f:
                    json.dump(self.intermediate_results, f, ensure_ascii=False, indent=2)
                self.logger.debug(f"中间结果已更新: {self.intermediate_file}")
            except Exception as e:
                self.logger.warning(f"保存中间结果失败: {e}")
    
    def _save_intermediate_results(self) -> Path:
        """异常时保存中间结果"""
        if not self.intermediate_results:
            return None
        
        recovery_file = self.output_dir / f"qs_recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(recovery_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "status": "interrupted",
                    "timestamp": datetime.now().isoformat(),
                    "completed_themes": len(self.intermediate_results),
                    "results": self.intermediate_results
                }, f, ensure_ascii=False, indent=2)
            
            return recovery_file
            
        except Exception as e:
            self.logger.error(f"保存恢复文件失败: {e}")
            return None
    
    async def _save_final_results(self, all_qs_pairs: List[Dict]) -> Path:
        """保存最终结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f"{self.config['qs_generation']['output_file_prefix']}_{self.db_name}_{timestamp}_pair.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_qs_pairs, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ 最终结果已保存到: {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"保存最终结果失败: {e}")
            raise
    
    def _cleanup_intermediate_file(self):
        """清理中间文件"""
        if self.intermediate_file and self.intermediate_file.exists():
            try:
                self.intermediate_file.unlink()
                self.logger.info("已清理中间文件")
            except Exception as e:
                self.logger.warning(f"清理中间文件失败: {e}")
    
    def _print_summary(self, report: Dict):
        """打印总结信息"""
        self.logger.info("=" * 60)
        self.logger.info("📊 生成总结")
        self.logger.info(f"  ✅ 总主题数: {report['total_themes']}")
        self.logger.info(f"  ✅ 成功主题: {report['successful_themes']}")
        
        if report['failed_themes']:
            self.logger.info(f"  ❌ 失败主题: {len(report['failed_themes'])}")
            for theme in report['failed_themes']:
                self.logger.info(f"     - {theme}")
        
        self.logger.info(f"  📝 总问题数: {report['total_questions']}")
        self.logger.info(f"  📁 输出文件: {report['output_file']}")
        self.logger.info(f"  ⏱️  执行时间: {report['execution_time']:.2f}秒")
        self.logger.info("=" * 60)

    async def _generate_metadata_file(self, themes: List[Dict]):
        """生成metadata.txt文件，包含INSERT语句"""
        metadata_file = self.output_dir / "metadata.txt"
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                f.write("-- Schema Tools生成的主题元数据\n")
                f.write(f"-- 业务背景: {self.business_context}\n")
                f.write(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"-- 数据库: {self.db_name}\n\n")
                
                f.write("-- 创建表（如果不存在）\n")
                f.write("CREATE TABLE IF NOT EXISTS metadata (\n")
                f.write("    id SERIAL PRIMARY KEY,\n")
                f.write("    topic_name VARCHAR(100) NOT NULL,\n")
                f.write("    description TEXT,\n")
                f.write("    related_tables TEXT[],\n")
                f.write("    keywords TEXT[],\n")
                f.write("    focus_areas TEXT[],\n")
                f.write("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n")
                f.write(");\n\n")
                
                f.write("-- 插入主题数据\n")
                for theme in themes:
                    # 获取字段值，使用新格式
                    topic_name = theme.get('topic_name', theme.get('name', ''))
                    description = theme.get('description', '')
                    
                    # 处理related_tables
                    related_tables = theme.get('related_tables', [])
                    if isinstance(related_tables, list):
                        tables_str = '{' + ','.join(related_tables) + '}'
                    else:
                        tables_str = '{}'
                    
                    # 处理keywords
                    keywords = theme.get('keywords', [])
                    if isinstance(keywords, list):
                        keywords_str = '{' + ','.join(keywords) + '}'
                    else:
                        keywords_str = '{}'
                    
                    # 处理focus_areas
                    focus_areas = theme.get('focus_areas', [])
                    if isinstance(focus_areas, list):
                        focus_areas_str = '{' + ','.join(focus_areas) + '}'
                    else:
                        focus_areas_str = '{}'
                    
                    # 生成INSERT语句
                    f.write("INSERT INTO metadata(topic_name, description, related_tables, keywords, focus_areas) VALUES\n")
                    f.write("(\n")
                    f.write(f"  '{self._escape_sql_string(topic_name)}',\n")
                    f.write(f"  '{self._escape_sql_string(description)}',\n")
                    f.write(f"  '{tables_str}',\n")
                    f.write(f"  '{keywords_str}',\n")
                    f.write(f"  '{focus_areas_str}'\n")
                    f.write(");\n\n")
            
            self.logger.info(f"✅ metadata.txt文件已生成: {metadata_file}")
            return metadata_file
            
        except Exception as e:
            self.logger.error(f"生成metadata.txt文件失败: {e}")
            return None
    
    def _escape_sql_string(self, value: str) -> str:
        """转义SQL字符串中的特殊字符"""
        if not value:
            return ""
        # 转义单引号
        return value.replace("'", "''") 