"""
元数据生成器 - 仅生成metadata.txt和db_query_decision_prompt.txt
不生成Question-SQL对，只提取主题并生成元数据文件
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from data_pipeline.analyzers import MDFileAnalyzer, ThemeExtractor
from data_pipeline.validators import FileCountValidator
from data_pipeline.utils.logger import setup_logging
from core.vanna_llm_factory import create_vanna_instance


class MetadataOnlyGenerator:
    """仅生成元数据文件的生成器"""
    
    def __init__(self, 
                 output_dir: str,
                 table_list_file: str,
                 business_context: str,
                 db_name: str = None):
        """
        初始化元数据生成器
        
        Args:
            output_dir: 输出目录（包含DDL和MD文件）
            table_list_file: 表清单文件路径
            business_context: 业务上下文
            db_name: 数据库名称
        """
        self.output_dir = Path(output_dir)
        self.table_list_file = table_list_file
        self.business_context = business_context
        self.db_name = db_name or "db"
        
        # 初始化组件
        self.validator = FileCountValidator()
        self.md_analyzer = MDFileAnalyzer(output_dir)
        self.vn = None
        self.theme_extractor = None
        
        print(f"🎯 元数据生成器初始化完成")
        print(f"📁 输出目录: {output_dir}")
        print(f"🏢 业务背景: {business_context}")
        print(f"💾 数据库: {self.db_name}")
    
    async def generate_metadata_only(self) -> Dict[str, Any]:
        """
        仅生成元数据文件
        
        Returns:
            生成结果报告
        """
        try:
            print("🚀 开始生成元数据文件...")
            
            # 1. 验证文件数量
            print("📋 验证文件数量...")
            validation_result = self.validator.validate(self.table_list_file, str(self.output_dir))
            
            if not validation_result.is_valid:
                print(f"❌ 文件验证失败: {validation_result.error}")
                if validation_result.missing_ddl:
                    print(f"缺失DDL文件: {validation_result.missing_ddl}")
                if validation_result.missing_md:
                    print(f"缺失MD文件: {validation_result.missing_md}")
                raise ValueError(f"文件验证失败: {validation_result.error}")
            
            print(f"✅ 文件验证通过: {validation_result.table_count}个表")
            
            # 2. 读取所有MD文件内容
            print("📖 读取MD文件...")
            md_contents = await self.md_analyzer.read_all_md_files()
            
            # 3. 初始化LLM相关组件
            self._initialize_llm_components()
            
            # 4. 提取分析主题
            print("🎯 提取分析主题...")
            themes = await self.theme_extractor.extract_themes(md_contents)
            print(f"✅ 成功提取 {len(themes)} 个分析主题")
            

            for i, theme in enumerate(themes):
                topic_name = theme.get('topic_name', theme.get('name', ''))
                description = theme.get('description', '')
                print(f"  {i+1}. {topic_name}: {description}")
            
            # 5. 生成metadata.txt文件
            print("📝 生成metadata.txt...")
            metadata_file = await self._generate_metadata_file(themes)
            
            # 6. 生成metadata_detail.md文件
            print("📝 生成metadata_detail.md...")
            metadata_md_file = await self._generate_metadata_md_file(themes)
            
            # 7. 生成db_query_decision_prompt.txt文件
            print("📝 生成db_query_decision_prompt.txt...")
            decision_prompt_file = await self._generate_decision_prompt_file(themes, md_contents)
            
            # 8. 生成报告
            report = {
                'success': True,
                'total_themes': len(themes),
                'metadata_file': str(metadata_file) if metadata_file else None,
                'metadata_md_file': str(metadata_md_file) if metadata_md_file else None,
                'decision_prompt_file': str(decision_prompt_file) if decision_prompt_file else None,
                'themes': themes
            }
            
            self._print_summary(report)
            
            return report
            
        except Exception as e:
            print(f"❌ 元数据生成失败: {e}")
            raise
    
    def _initialize_llm_components(self):
        """初始化LLM相关组件"""
        if not self.vn:
            print("🤖 初始化LLM组件...")
            self.vn = create_vanna_instance()
            self.theme_extractor = ThemeExtractor(self.vn, self.business_context)
    
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
            
            print(f"✅ metadata.txt文件已生成: {metadata_file}")
            return metadata_file
            
        except Exception as e:
            print(f"❌ 生成metadata.txt文件失败: {e}")
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
            
            print(f"✅ metadata_detail.md文件已生成: {metadata_md_file}")
            return metadata_md_file
            
        except Exception as e:
            print(f"❌ 生成metadata_detail.md文件失败: {e}")
            return None
    
    async def _generate_decision_prompt_file(self, themes: List[Dict], md_contents: str):
        """生成db_query_decision_prompt.txt文件"""
        decision_prompt_file = self.output_dir / "db_query_decision_prompt.txt"
        
        try:
            # 使用LLM动态生成决策提示内容
            decision_content = await self._generate_decision_prompt_with_llm(themes, md_contents)
            
            # 写入文件
            with open(decision_prompt_file, 'w', encoding='utf-8') as f:
                f.write(decision_content)
            
            print(f"✅ db_query_decision_prompt.txt文件已生成: {decision_prompt_file}")
            return decision_prompt_file
            
        except Exception as e:
            print(f"❌ 生成db_query_decision_prompt.txt文件失败: {e}")
            # 如果LLM调用失败，使用回退方案
            try:
                fallback_content = await self._generate_fallback_decision_content(themes)
                with open(decision_prompt_file, 'w', encoding='utf-8') as f:
                    f.write(fallback_content)
                print(f"⚠️ 使用回退方案生成了 {decision_prompt_file}")
                return decision_prompt_file
            except Exception as fallback_error:
                print(f"❌ 回退方案也失败: {fallback_error}")
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
            response = await asyncio.to_thread(
                self.vn.chat_with_llm,
                question=prompt,
                system_prompt="你是一个专业的数据分析师，擅长从业务角度总结数据库的业务范围和核心实体。请基于实际的表结构和字段信息生成准确的业务描述。"
            )
            return response.strip()
            
        except Exception as e:
            print(f"❌ LLM生成决策提示内容失败: {e}")
            # 回退方案：生成基础内容
            return await self._generate_fallback_decision_content(themes)
    
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

            data_range = await asyncio.to_thread(
                self.vn.chat_with_llm,
                question=simple_prompt,
                system_prompt="请用简洁的语言概括数据范围。"
            )
            data_range = data_range.strip()
            
            # 如果LLM返回内容合理，则使用
            if data_range and len(data_range) < 100:
                content += f"当前数据库存储的是{self.business_context}的相关数据，主要涉及{data_range}，包含以下业务数据：\n"
            else:
                raise Exception("LLM返回内容不合理")
                
        except Exception as e:
            print(f"⚠️ 简化LLM调用也失败，使用完全兜底方案: {e}")
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
    
    def _escape_sql_string(self, value: str) -> str:
        """转义SQL字符串中的特殊字符"""
        if not value:
            return ""
        # 转义单引号
        return value.replace("'", "''")
    
    def _print_summary(self, report: Dict):
        """打印总结信息"""
        print("=" * 60)
        print("📊 元数据生成总结")
        print(f"  ✅ 分析主题数: {report['total_themes']}")
        print(f"  📄 metadata.txt: {'✅ 已生成' if report['metadata_file'] else '❌ 生成失败'}")
        print(f"  📄 metadata_detail.md: {'✅ 已生成' if report['metadata_md_file'] else '❌ 生成失败'}")
        print(f"  📄 db_query_decision_prompt.txt: {'✅ 已生成' if report['decision_prompt_file'] else '❌ 生成失败'}")
        print("=" * 60)


def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='元数据生成器 - 仅生成metadata.txt和db_query_decision_prompt.txt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本使用
  python -m data_pipeline.metadata_only_generator --output-dir ./data_pipeline/training_data --table-list ./data_pipeline/tables.txt --business-context "高速公路服务区管理系统"
  
  # 指定数据库名称
  python -m data_pipeline.metadata_only_generator --output-dir ./data_pipeline/training_data --table-list ./data_pipeline/tables.txt --business-context "电商系统" --db-name ecommerce_db
  
  # 启用详细日志
  python -m data_pipeline.metadata_only_generator --output-dir ./data_pipeline/training_data --table-list ./data_pipeline/tables.txt --business-context "管理系统" --verbose
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--output-dir',
        required=True,
        help='包含DDL和MD文件的输出目录'
    )
    
    parser.add_argument(
        '--table-list',
        required=True,
        help='表清单文件路径（用于验证文件数量）'
    )
    
    parser.add_argument(
        '--business-context',
        required=True,
        help='业务上下文描述'
    )
    
    # 可选参数
    parser.add_argument(
        '--db-name',
        help='数据库名称（用于输出文件命名）'
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


async def main():
    """主入口函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(
        verbose=args.verbose,
        log_file=args.log_file
    )
    
    # 验证参数
    output_path = Path(args.output_dir)
    if not output_path.exists():
        print(f"错误: 输出目录不存在: {args.output_dir}")
        sys.exit(1)
    
    if not os.path.exists(args.table_list):
        print(f"错误: 表清单文件不存在: {args.table_list}")
        sys.exit(1)
    
    try:
        # 创建生成器
        generator = MetadataOnlyGenerator(
            output_dir=args.output_dir,
            table_list_file=args.table_list,
            business_context=args.business_context,
            db_name=args.db_name
        )
        
        # 执行生成
        report = await generator.generate_metadata_only()
        
        # 输出结果
        if report['success']:
            print("\n🎉 元数据文件生成成功!")
            exit_code = 0
        else:
            print("\n❌ 元数据文件生成失败")
            exit_code = 1
        
        sys.exit(exit_code)
        
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