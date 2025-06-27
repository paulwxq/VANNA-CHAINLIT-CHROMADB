import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from data_pipeline.config import SCHEMA_TOOLS_CONFIG
from data_pipeline.validators import FileCountValidator
from data_pipeline.analyzers import MDFileAnalyzer, ThemeExtractor
from data_pipeline.utils.logger import setup_logging
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
            
            # 8.6 生成metadata_detail.md文件
            await self._generate_metadata_md_file(themes)
            
            # 8.7 生成db_query_decision_prompt.txt文件
            await self._generate_decision_prompt_file(themes)
            
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
        
        # 获取主题信息
        topic_name = theme.get('topic_name', theme.get('name', ''))
        description = theme.get('description', '')
        biz_entities = theme.get('biz_entities', [])
        biz_metrics = theme.get('biz_metrics', [])
        related_tables = theme.get('related_tables', [])
        
        prompt = f"""你是一位业务数据分析师，正在为{self.business_context}设计数据查询。

当前分析主题：{topic_name}
主题描述：{description}
业务实体：{', '.join(biz_entities)}
业务指标：{', '.join(biz_metrics)}
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
                f.write("    id SERIAL PRIMARY KEY,    -- 主键\n")
                f.write("    topic_name VARCHAR(100) NOT NULL,  -- 业务主题名称\n")
                f.write("    description TEXT,                  -- 业务主体说明\n")
                f.write("    related_tables TEXT[],\t\t\t  -- 相关表名\n")
                f.write("    biz_entities TEXT[],               -- 主要业务实体名称\n")
                f.write("    biz_metrics TEXT[],                -- 主要业务指标名称\n")
                f.write("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP    -- 插入时间\n")
                f.write(");\n\n")
                
                f.write("-- 插入主题数据\n")
                for theme in themes:
                    # 获取字段值，使用新格式
                    topic_name = theme.get('topic_name', theme.get('name', ''))
                    description = theme.get('description', '')
                    
                    # 处理related_tables
                    related_tables = theme.get('related_tables', [])
                    if isinstance(related_tables, list):
                        tables_str = ','.join(related_tables)
                    else:
                        tables_str = ''
                    
                    # 处理biz_entities
                    biz_entities = theme.get('biz_entities', [])
                    if isinstance(biz_entities, list):
                        entities_str = ','.join(biz_entities)
                    else:
                        entities_str = ''
                    
                    # 处理biz_metrics
                    biz_metrics = theme.get('biz_metrics', [])
                    if isinstance(biz_metrics, list):
                        metrics_str = ','.join(biz_metrics)
                    else:
                        metrics_str = ''
                    
                    # 生成INSERT语句
                    f.write("INSERT INTO metadata(topic_name, description, related_tables, biz_entities, biz_metrics) VALUES\n")
                    f.write("(\n")
                    f.write(f"  '{self._escape_sql_string(topic_name)}',\n")
                    f.write(f"  '{self._escape_sql_string(description)}',\n")
                    f.write(f"  '{tables_str}',\n")
                    f.write(f"  '{entities_str}',\n")
                    f.write(f"  '{metrics_str}'\n")
                    f.write(");\n\n")
            
            self.logger.info(f"✅ metadata.txt文件已生成: {metadata_file}")
            return metadata_file
            
        except Exception as e:
            self.logger.error(f"生成metadata.txt文件失败: {e}")
            return None
    
    async def _generate_metadata_md_file(self, themes: List[Dict]):
        """生成metadata_detail.md文件"""
        metadata_md_file = self.output_dir / "metadata_detail.md"
        
        try:
            # 从themes中收集示例数据
            sample_tables = set()
            sample_entities = set()
            sample_metrics = set()
            
            for theme in themes:
                related_tables = theme.get('related_tables', [])
                if isinstance(related_tables, list):
                    sample_tables.update(related_tables[:2])  # 取前2个表作为示例
                
                biz_entities = theme.get('biz_entities', [])
                if isinstance(biz_entities, list):
                    sample_entities.update(biz_entities[:3])  # 取前3个实体作为示例
                
                biz_metrics = theme.get('biz_metrics', [])
                if isinstance(biz_metrics, list):
                    sample_metrics.update(biz_metrics[:3])  # 取前3个指标作为示例
            
            # 转换为字符串格式，避免硬编码特定行业内容
            tables_example = ', '.join(list(sample_tables)[:2]) if sample_tables else '数据表1, 数据表2'
            entities_example = ', '.join(list(sample_entities)[:3]) if sample_entities else '业务实体1, 业务实体2, 业务实体3'
            metrics_example = ', '.join(list(sample_metrics)[:3]) if sample_metrics else '业务指标1, 业务指标2, 业务指标3'
            
            with open(metadata_md_file, 'w', encoding='utf-8') as f:
                f.write("## metadata（存储分析主题元数据）\n\n")
                f.write("`metadata` 主要描述了当前数据库包含了哪些数据内容，哪些分析主题，哪些指标等等。\n\n")
                f.write("字段列表：\n\n")
                f.write("- `id` (serial) - 主键ID [主键, 非空]\n")
                f.write("- `topic_name` (varchar(100)) - 业务主题名称 [非空]\n")
                f.write("- `description` (text) - 业务主题说明\n")
                f.write(f"- `related_tables` (text[]) - 涉及的数据表 [示例: {tables_example}]\n")
                f.write(f"- `biz_entities` (text[]) - 主要业务实体名称 [示例: {entities_example}]\n")
                f.write(f"- `biz_metrics` (text[]) - 主要业务指标名称 [示例: {metrics_example}]\n")
                f.write("- `created_at` (timestamp) - 插入时间 [默认值: `CURRENT_TIMESTAMP`]\n\n")
                f.write("字段补充说明：\n\n")
                f.write("- `id` 为主键，自增；\n")
                f.write("- `related_tables` 用于建立主题与具体明细表的依赖关系；\n")
                f.write("- `biz_entities` 表示主题关注的核心对象，例如服务区、车辆、公司；\n")
                f.write("- `biz_metrics` 表示该主题关注的业务分析指标，例如营收对比、趋势变化、占比结构等。\n")
            
            self.logger.info(f"✅ metadata_detail.md文件已生成: {metadata_md_file}")
            return metadata_md_file
            
        except Exception as e:
            self.logger.error(f"生成metadata_detail.md文件失败: {e}")
            return None
    
    async def _generate_decision_prompt_with_llm(self, themes: List[Dict], md_contents: str) -> str:
        """使用LLM动态生成db_query_decision_prompt.txt的完整内容（基于纯表结构分析）"""
        try:
            # 构建LLM提示词 - 让LLM完全独立分析表结构
            prompt = f"""你是一位资深的数据分析师，请直接分析以下数据库的表结构，独立判断业务范围和数据范围。

业务背景：{self.business_context}

数据库表结构详细信息：
{md_contents}

分析任务：
请你直接从表结构、字段名称、字段类型、示例数据中推断业务逻辑，不要参考任何预设的业务主题。

分析要求：
1. **业务范围**：根据表名和核心业务字段，用一句话概括这个数据库支撑的业务领域
2. **数据范围**：根据具体的数据字段（如金额、数量、类型等），用一句话概括涉及的数据类型和范围  
3. **核心业务实体**：从非技术字段中识别主要的业务对象（如表中的维度字段）
4. **关键业务指标**：从数值型字段和枚举字段中识别可以进行分析的指标

技术字段过滤规则（请忽略以下字段）：
- 主键字段：id、主键ID等
- 时间戳字段：create_ts、update_ts、delete_ts、created_at、updated_at等  
- 版本字段：version、版本号等
- 操作人字段：created_by、updated_by、deleted_by等

请直接生成以下格式的业务分析报告（请严格按照格式，不要添加额外内容）：

=== 数据库业务范围 ===
当前数据库存储的是[业务描述]的相关数据，主要涉及[数据范围]，包含以下业务数据：
核心业务实体：
- 实体类型1：详细描述（基于实际字段和业务场景），主要字段：字段1、字段2、字段3
- 实体类型2：详细描述，主要字段：字段1、字段2、字段3
关键业务指标：
- 指标类型1：详细描述（基于实际数值字段和分析需求）
- 指标类型2：详细描述

要求：
1. 请完全基于表结构进行独立分析，从字段的业务含义出发，准确反映数据库的实际业务范围
2. 严格按照上述格式输出，不要添加分析依据、总结或其他额外内容
3. 输出内容到"指标类型2：详细描述"结束即可"""
            
            # 调用LLM生成内容
            response = await self._call_llm(prompt)
            return response.strip()
            
        except Exception as e:
            self.logger.error(f"LLM生成决策提示内容失败: {e}")
            # 回退方案：生成基础内容
            return self._generate_fallback_decision_content(themes)
    
    async def _generate_fallback_decision_content(self, themes: List[Dict]) -> str:
        """生成回退的决策提示内容（尝试用简化LLM调用）"""
        content = f"=== 数据库业务范围 ===\n"
        
        # 尝试用简化的LLM调用获取数据范围
        try:
            # 构建简化的提示词
            entities_sample = []
            metrics_sample = []
            
            for theme in themes[:3]:  # 只取前3个主题作为示例
                biz_entities = theme.get('biz_entities', [])
                if isinstance(biz_entities, list):
                    entities_sample.extend(biz_entities[:2])
                    
                biz_metrics = theme.get('biz_metrics', [])  
                if isinstance(biz_metrics, list):
                    metrics_sample.extend(biz_metrics[:2])
            
            # 简化的提示词
            simple_prompt = f"""基于以下信息，用一句话概括{self.business_context}涉及的数据范围：
业务实体示例：{', '.join(entities_sample[:5])}
业务指标示例：{', '.join(metrics_sample[:5])}

请只回答数据范围，格式如：某某数据、某某信息、某某统计等"""

            data_range = await self._call_llm(simple_prompt)
            data_range = data_range.strip()
            
            # 如果LLM返回内容合理，则使用
            if data_range and len(data_range) < 100:
                content += f"当前数据库存储的是{self.business_context}的相关数据，主要涉及{data_range}，包含以下业务数据：\n"
            else:
                raise Exception("LLM返回内容不合理")
                
        except Exception as e:
            self.logger.warning(f"简化LLM调用也失败，使用完全兜底方案: {e}")
            # 真正的最后兜底
            content += f"当前数据库存储的是{self.business_context}的相关数据，主要涉及相关业务数据，包含以下业务数据：\n"
        
        content += "核心业务实体：\n"
        
        # 收集所有实体
        all_entities = set()
        for theme in themes:
            biz_entities = theme.get('biz_entities', [])
            if isinstance(biz_entities, list):
                all_entities.update(biz_entities)
        
        for entity in list(all_entities)[:8]:
            content += f"- {entity}：{entity}相关的业务信息\n"
        
        content += "关键业务指标：\n"
        
        # 收集所有指标
        all_metrics = set()
        for theme in themes:
            biz_metrics = theme.get('biz_metrics', [])
            if isinstance(biz_metrics, list):
                all_metrics.update(biz_metrics)
        
        for metric in list(all_metrics)[:8]:
            content += f"- {metric}：{metric}相关的分析指标\n"
        
        return content

    async def _generate_decision_prompt_file(self, themes: List[Dict]):
        """生成db_query_decision_prompt.txt文件"""
        decision_prompt_file = self.output_dir / "db_query_decision_prompt.txt"
        
        try:
            # 读取MD内容作为LLM输入
            md_contents = await self.md_analyzer.read_all_md_files()
            
            # 使用LLM动态生成决策提示内容
            decision_content = await self._generate_decision_prompt_with_llm(themes, md_contents)
            
            # 写入文件
            with open(decision_prompt_file, 'w', encoding='utf-8') as f:
                f.write(decision_content)
            
            self.logger.info(f"✅ db_query_decision_prompt.txt文件已生成: {decision_prompt_file}")
            return decision_prompt_file
            
        except Exception as e:
            self.logger.error(f"生成db_query_decision_prompt.txt文件失败: {e}")
            # 如果LLM调用失败，使用回退方案
            try:
                fallback_content = await self._generate_fallback_decision_content(themes)
                with open(decision_prompt_file, 'w', encoding='utf-8') as f:
                    f.write(fallback_content)
                self.logger.warning(f"⚠️ 使用回退方案生成了 {decision_prompt_file}")
                return decision_prompt_file
            except Exception as fallback_error:
                self.logger.error(f"回退方案也失败: {fallback_error}")
                return None
    
    def _escape_sql_string(self, value: str) -> str:
        """转义SQL字符串中的特殊字符"""
        if not value:
            return ""
        # 转义单引号
        return value.replace("'", "''") 