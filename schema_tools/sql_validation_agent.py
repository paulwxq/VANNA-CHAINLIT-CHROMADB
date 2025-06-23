import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from schema_tools.config import SCHEMA_TOOLS_CONFIG
from schema_tools.validators import SQLValidator, SQLValidationResult, ValidationStats
from schema_tools.utils.logger import setup_logging


class SQLValidationAgent:
    """SQL验证Agent - 管理SQL验证的完整流程"""
    
    def __init__(self, 
                 db_connection: str,
                 input_file: str,
                 output_dir: str = None):
        """
        初始化SQL验证Agent
        
        Args:
            db_connection: 数据库连接字符串
            input_file: 输入的JSON文件路径（包含Question-SQL对）
            output_dir: 输出目录（默认为输入文件同目录）
        """
        self.db_connection = db_connection
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir) if output_dir else self.input_file.parent
        
        self.config = SCHEMA_TOOLS_CONFIG['sql_validation']
        self.logger = logging.getLogger("schema_tools.SQLValidationAgent")
        
        # 初始化验证器
        self.validator = SQLValidator(db_connection)
        
        # 初始化LLM实例（用于SQL修复）
        self.vn = None
        if self.config.get('enable_sql_repair', True):
            self._initialize_llm()
        
        # 统计信息
        self.total_questions = 0
        self.validation_start_time = None
        
    async def validate(self) -> Dict[str, Any]:
        """
        执行SQL验证流程
        
        Returns:
            验证结果报告
        """
        try:
            self.validation_start_time = time.time()
            self.logger.info("🚀 开始SQL验证流程")
            
            # 1. 读取输入文件
            self.logger.info(f"📖 读取输入文件: {self.input_file}")
            questions_sqls = await self._load_questions_sqls()
            self.total_questions = len(questions_sqls)
            
            if not questions_sqls:
                raise ValueError("输入文件中没有找到有效的Question-SQL对")
            
            self.logger.info(f"✅ 成功读取 {self.total_questions} 个Question-SQL对")
            
            # 2. 提取SQL语句
            sqls = [item['sql'] for item in questions_sqls]
            
            # 3. 执行验证
            self.logger.info("🔍 开始SQL验证...")
            validation_results = await self._validate_sqls_with_batching(sqls)
            
            # 4. 计算统计信息
            stats = self.validator.calculate_stats(validation_results)
            
            # 5. 尝试修复失败的SQL（如果启用LLM修复）
            file_modification_stats = {'modified': 0, 'deleted': 0, 'failed_modifications': 0}
            if self.config.get('enable_sql_repair', False) and self.vn:
                self.logger.info("🔧 启用LLM修复功能，开始修复失败的SQL...")
                validation_results = await self._attempt_sql_repair(questions_sqls, validation_results)
                # 重新计算统计信息（包含修复结果）
                stats = self.validator.calculate_stats(validation_results)
            
            # 6. 修改原始JSON文件（如果启用文件修改）
            if self.config.get('modify_original_file', False):
                self.logger.info("📝 启用文件修改功能，开始修改原始JSON文件...")
                file_modification_stats = await self._modify_original_json_file(questions_sqls, validation_results)
            else:
                self.logger.info("📋 不修改原始文件")
            
            # 7. 生成详细报告
            report = await self._generate_report(questions_sqls, validation_results, stats, file_modification_stats)
            
            # 8. 保存验证报告
            if self.config['save_validation_report']:
                await self._save_validation_report(report)
            
            # 9. 输出结果摘要
            self._print_summary(stats, validation_results, file_modification_stats)
            
            return report
            
        except Exception as e:
            self.logger.exception("❌ SQL验证流程失败")
            raise
    
    async def _load_questions_sqls(self) -> List[Dict[str, str]]:
        """读取Question-SQL对"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证数据格式
            if not isinstance(data, list):
                raise ValueError("输入文件应包含Question-SQL对的数组")
            
            questions_sqls = []
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    self.logger.warning(f"跳过第 {i+1} 项：格式不正确")
                    continue
                
                if 'question' not in item or 'sql' not in item:
                    self.logger.warning(f"跳过第 {i+1} 项：缺少question或sql字段")
                    continue
                
                questions_sqls.append({
                    'index': i,
                    'question': item['question'],
                    'sql': item['sql'].strip()
                })
            
            return questions_sqls
            
        except json.JSONDecodeError as e:
            raise ValueError(f"输入文件不是有效的JSON格式: {e}")
        except Exception as e:
            raise ValueError(f"读取输入文件失败: {e}")
    
    async def _validate_sqls_with_batching(self, sqls: List[str]) -> List[SQLValidationResult]:
        """使用批处理方式验证SQL"""
        batch_size = self.config['batch_size']
        all_results = []
        
        # 分批处理
        for i in range(0, len(sqls), batch_size):
            batch = sqls[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(sqls) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 处理批次 {batch_num}/{total_batches} ({len(batch)} 个SQL)")
            
            batch_results = await self.validator.validate_sqls_batch(batch)
            all_results.extend(batch_results)
            
            # 显示批次进度
            valid_count = sum(1 for r in batch_results if r.valid)
            self.logger.info(f"✅ 批次 {batch_num} 完成: {valid_count}/{len(batch)} 有效")
        
        return all_results
    
    async def _generate_report(self, 
                              questions_sqls: List[Dict], 
                              validation_results: List[SQLValidationResult],
                              stats: ValidationStats,
                              file_modification_stats: Dict[str, int] = None) -> Dict[str, Any]:
        """生成详细验证报告"""
        
        validation_time = time.time() - self.validation_start_time
        
        # 合并问题和验证结果
        detailed_results = []
        for i, (qs, result) in enumerate(zip(questions_sqls, validation_results)):
            detailed_results.append({
                'index': i + 1,
                'question': qs['question'],
                'sql': qs['sql'],
                'valid': result.valid,
                'error_message': result.error_message,
                'execution_time': result.execution_time,
                'retry_count': result.retry_count,
                
                # 添加修复信息
                'repair_attempted': result.repair_attempted,
                'repair_successful': result.repair_successful,
                'repaired_sql': result.repaired_sql,
                'repair_error': result.repair_error
            })
        
        # 生成报告
        report = {
            'metadata': {
                'input_file': str(self.input_file),
                'validation_time': datetime.now().isoformat(),
                'total_validation_time': validation_time,
                'database_connection': self._mask_connection_string(self.db_connection),
                'config': self.config.copy()
            },
            'summary': {
                'total_questions': stats.total_sqls,
                'valid_sqls': stats.valid_sqls,
                'invalid_sqls': stats.invalid_sqls,
                'success_rate': stats.valid_sqls / stats.total_sqls if stats.total_sqls > 0 else 0.0,
                'average_execution_time': stats.avg_time_per_sql,
                'total_retries': stats.retry_count,
                
                # 添加修复统计
                'repair_stats': {
                    'attempted': stats.repair_attempted,
                    'successful': stats.repair_successful,
                    'failed': stats.repair_failed
                },
                
                # 添加文件修改统计
                'file_modification_stats': file_modification_stats or {
                    'modified': 0, 'deleted': 0, 'failed_modifications': 0
                }
            },
            'detailed_results': detailed_results
        }
        
        return report
    
    async def _save_validation_report(self, report: Dict[str, Any]):
        """保存验证报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 只保存文本格式摘要（便于查看）
        txt_file = self.output_dir / f"{self.config['report_file_prefix']}_{timestamp}_summary.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"SQL验证报告\n")
            f.write(f"=" * 50 + "\n\n")
            f.write(f"输入文件: {self.input_file}\n")
            f.write(f"验证时间: {report['metadata']['validation_time']}\n")
            f.write(f"验证耗时: {report['metadata']['total_validation_time']:.2f}秒\n\n")
            
            f.write(f"验证结果摘要:\n")
            f.write(f"  总SQL数量: {report['summary']['total_questions']}\n")
            f.write(f"  有效SQL: {report['summary']['valid_sqls']}\n")
            f.write(f"  无效SQL: {report['summary']['invalid_sqls']}\n")
            f.write(f"  成功率: {report['summary']['success_rate']:.2%}\n")
            f.write(f"  平均耗时: {report['summary']['average_execution_time']:.3f}秒\n")
            f.write(f"  重试次数: {report['summary']['total_retries']}\n\n")
            
            # 添加修复统计
            if 'repair_stats' in report['summary']:
                repair_stats = report['summary']['repair_stats']
                f.write(f"SQL修复统计:\n")
                f.write(f"  尝试修复: {repair_stats['attempted']}\n")
                f.write(f"  修复成功: {repair_stats['successful']}\n")
                f.write(f"  修复失败: {repair_stats['failed']}\n")
                if repair_stats['attempted'] > 0:
                    f.write(f"  修复成功率: {repair_stats['successful'] / repair_stats['attempted']:.2%}\n")
                f.write(f"\n")
            
            # 添加文件修改统计
            if 'file_modification_stats' in report['summary']:
                file_stats = report['summary']['file_modification_stats']
                f.write(f"原始文件修改统计:\n")
                f.write(f"  修改的SQL: {file_stats['modified']}\n")
                f.write(f"  删除的无效项: {file_stats['deleted']}\n")
                f.write(f"  修改失败: {file_stats['failed_modifications']}\n")
                f.write(f"\n")
            
            # 提取错误详情（显示完整SQL）
            error_results = [r for r in report['detailed_results'] if not r['valid'] and not r.get('repair_successful', False)]
            if error_results:
                f.write(f"错误详情（共{len(error_results)}个）:\n")
                f.write(f"=" * 50 + "\n")
                for i, error_result in enumerate(error_results, 1):
                    f.write(f"\n{i}. 问题: {error_result['question']}\n")
                    f.write(f"   错误: {error_result['error_message']}\n")
                    if error_result['retry_count'] > 0:
                        f.write(f"   重试: {error_result['retry_count']}次\n")
                    
                    # 显示修复尝试信息
                    if error_result.get('repair_attempted', False):
                        if error_result.get('repair_successful', False):
                            f.write(f"   LLM修复尝试: 成功\n")
                            f.write(f"   修复后SQL:\n")
                            f.write(f"   {error_result.get('repaired_sql', '')}\n")
                        else:
                            f.write(f"   LLM修复尝试: 失败\n")
                            repair_error = error_result.get('repair_error', '未知错误')
                            f.write(f"   修复失败原因: {repair_error}\n")
                    else:
                        f.write(f"   LLM修复尝试: 未尝试\n")
                    
                    f.write(f"   完整SQL:\n")
                    f.write(f"   {error_result['sql']}\n")
                    f.write(f"   {'-' * 40}\n")
            
            # 显示成功修复的SQL
            repaired_results = [r for r in report['detailed_results'] if r.get('repair_successful', False)]
            if repaired_results:
                f.write(f"\n成功修复的SQL（共{len(repaired_results)}个）:\n")
                f.write(f"=" * 50 + "\n")
                for i, repaired_result in enumerate(repaired_results, 1):
                    f.write(f"\n{i}. 问题: {repaired_result['question']}\n")
                    f.write(f"   原始错误: {repaired_result['error_message']}\n")
                    f.write(f"   修复后SQL:\n")
                    f.write(f"   {repaired_result.get('repaired_sql', '')}\n")
                    f.write(f"   {'-' * 40}\n")
        
        self.logger.info(f"📊 验证报告已保存: {txt_file}")
        
        # 如果配置允许，也可以保存JSON格式的详细报告（可选）
        if self.config.get('save_detailed_json_report', False):
            json_file = self.output_dir / f"{self.config['report_file_prefix']}_{timestamp}_report.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"📊 详细JSON报告已保存: {json_file}")
    
    def _mask_connection_string(self, conn_str: str) -> str:
        """隐藏连接字符串中的敏感信息"""
        import re
        # 隐藏密码
        return re.sub(r':[^:@]+@', ':***@', conn_str)
    
    def _print_summary(self, stats: ValidationStats, validation_results: List[SQLValidationResult] = None, file_modification_stats: Dict[str, int] = None):
        """打印验证结果摘要"""
        validation_time = time.time() - self.validation_start_time
        
        self.logger.info("=" * 60)
        self.logger.info("📊 SQL验证结果摘要")
        self.logger.info(f"  📝 总SQL数量: {stats.total_sqls}")
        self.logger.info(f"  ✅ 有效SQL: {stats.valid_sqls}")
        self.logger.info(f"  ❌ 无效SQL: {stats.invalid_sqls}")
        self.logger.info(f"  📈 成功率: {stats.valid_sqls / stats.total_sqls:.2%}")
        self.logger.info(f"  ⏱️  平均耗时: {stats.avg_time_per_sql:.3f}秒/SQL")
        self.logger.info(f"  🔄 重试次数: {stats.retry_count}")
        self.logger.info(f"  ⏰ 总耗时: {validation_time:.2f}秒")
        
        # 添加修复统计
        if stats.repair_attempted > 0:
            self.logger.info(f"  🔧 修复尝试: {stats.repair_attempted}")
            self.logger.info(f"  ✅ 修复成功: {stats.repair_successful}")
            self.logger.info(f"  ❌ 修复失败: {stats.repair_failed}")
            repair_rate = stats.repair_successful / stats.repair_attempted if stats.repair_attempted > 0 else 0.0
            self.logger.info(f"  📈 修复成功率: {repair_rate:.2%}")
        
        # 添加文件修改统计
        if file_modification_stats:
            self.logger.info(f"  📝 文件修改: {file_modification_stats['modified']} 个SQL")
            self.logger.info(f"  🗑️  删除无效项: {file_modification_stats['deleted']} 个")
            if file_modification_stats['failed_modifications'] > 0:
                self.logger.info(f"  ⚠️  修改失败: {file_modification_stats['failed_modifications']} 个")
        
        self.logger.info("=" * 60)
        
        # 显示部分错误信息
        if validation_results:
            error_results = [r for r in validation_results if not r.valid]
            if error_results:
                self.logger.info(f"⚠️  前5个错误示例:")
                for i, error_result in enumerate(error_results[:5], 1):
                    self.logger.info(f"  {i}. {error_result.error_message}")
                    # 显示SQL的前80个字符
                    sql_preview = error_result.sql[:80] + '...' if len(error_result.sql) > 80 else error_result.sql
                    self.logger.info(f"     SQL: {sql_preview}")
    
    def _initialize_llm(self):
        """初始化LLM实例"""
        try:
            from core.vanna_llm_factory import create_vanna_instance
            self.vn = create_vanna_instance()
            self.logger.info("✅ LLM实例初始化成功，SQL修复功能已启用")
        except Exception as e:
            self.logger.warning(f"⚠️  LLM初始化失败，SQL修复功能将被禁用: {e}")
            self.vn = None 
    
    async def _attempt_sql_repair(self, questions_sqls: List[Dict], validation_results: List[SQLValidationResult]) -> List[SQLValidationResult]:
        """
        尝试修复失败的SQL
        
        Args:
            questions_sqls: 问题SQL对列表
            validation_results: 验证结果列表
            
        Returns:
            更新后的验证结果列表
        """
        # 找出需要修复的SQL
        failed_indices = []
        for i, result in enumerate(validation_results):
            if not result.valid:
                failed_indices.append(i)
        
        if not failed_indices:
            self.logger.info("🎉 所有SQL都有效，无需修复")
            return validation_results
        
        self.logger.info(f"🔧 开始修复 {len(failed_indices)} 个失败的SQL...")
        
        # 批量修复
        batch_size = self.config.get('repair_batch_size', 5)
        updated_results = validation_results.copy()
        
        for i in range(0, len(failed_indices), batch_size):
            batch_indices = failed_indices[i:i + batch_size]
            self.logger.info(f"📦 修复批次 {i//batch_size + 1}/{(len(failed_indices) + batch_size - 1)//batch_size} ({len(batch_indices)} 个SQL)")
            
            # 准备批次数据
            batch_data = []
            for idx in batch_indices:
                batch_data.append({
                    'index': idx,
                    'question': questions_sqls[idx]['question'],
                    'sql': validation_results[idx].sql,
                    'error': validation_results[idx].error_message
                })
            
            # 调用LLM修复
            repaired_sqls = await self._repair_sqls_with_llm(batch_data)
            
            # 验证修复后的SQL
            for j, idx in enumerate(batch_indices):
                original_result = updated_results[idx]
                original_result.repair_attempted = True
                
                if j < len(repaired_sqls) and repaired_sqls[j]:
                    repaired_sql = repaired_sqls[j]
                    
                    # 验证修复后的SQL
                    repair_result = await self.validator.validate_sql(repaired_sql)
                    
                    if repair_result.valid:
                        # 修复成功
                        original_result.repair_successful = True
                        original_result.repaired_sql = repaired_sql
                        original_result.valid = True  # 更新为有效
                        self.logger.info(f"✅ SQL修复成功 (索引 {idx})")
                    else:
                        # 修复失败
                        original_result.repair_successful = False
                        original_result.repair_error = repair_result.error_message
                        self.logger.warning(f"❌ SQL修复失败 (索引 {idx}): {repair_result.error_message}")
                else:
                    # LLM修复失败
                    original_result.repair_successful = False
                    original_result.repair_error = "LLM修复失败或返回空结果"
                    self.logger.warning(f"❌ LLM修复失败 (索引 {idx})")
        
        # 统计修复结果
        repair_attempted = sum(1 for r in updated_results if r.repair_attempted)
        repair_successful = sum(1 for r in updated_results if r.repair_successful)
        
        self.logger.info(f"🔧 修复完成: {repair_successful}/{repair_attempted} 成功")
        
        return updated_results 
    
    async def _modify_original_json_file(self, questions_sqls: List[Dict], validation_results: List[SQLValidationResult]) -> Dict[str, int]:
        """
        修改原始JSON文件：
        1. 对于修复成功的SQL，更新原始文件中的SQL内容
        2. 对于无法修复的SQL，从原始文件中删除对应的键值对
        
        Returns:
            修改统计信息
        """
        stats = {'modified': 0, 'deleted': 0, 'failed_modifications': 0}
        
        try:
            # 读取原始JSON文件
            with open(self.input_file, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            if not isinstance(original_data, list):
                self.logger.error("原始JSON文件格式不正确，无法修改")
                stats['failed_modifications'] = 1
                return stats
            
            # 创建备份文件
            backup_file = Path(str(self.input_file) + '.backup')
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(original_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已创建备份文件: {backup_file}")
            
            # 构建修改计划
            modifications = []
            deletions = []
            
            for i, (qs, result) in enumerate(zip(questions_sqls, validation_results)):
                if result.repair_successful and result.repaired_sql:
                    # 修复成功的SQL
                    modifications.append({
                        'index': i,
                        'original_sql': result.sql,
                        'repaired_sql': result.repaired_sql,
                        'question': qs['question']
                    })
                elif not result.valid and not result.repair_successful:
                    # 无法修复的SQL，标记删除
                    deletions.append({
                        'index': i,
                        'question': qs['question'],
                        'sql': result.sql,
                        'error': result.error_message
                    })
            
            # 执行修改（从后往前，避免索引变化）
            new_data = original_data.copy()
            
            # 先删除无效项（从后往前删除）
            for deletion in sorted(deletions, key=lambda x: x['index'], reverse=True):
                if deletion['index'] < len(new_data):
                    removed_item = new_data.pop(deletion['index'])
                    stats['deleted'] += 1
                    self.logger.info(f"删除无效项 {deletion['index']}: {deletion['question'][:50]}...")
            
            # 再修改SQL（需要重新计算索引）
            index_offset = 0
            for modification in sorted(modifications, key=lambda x: x['index']):
                # 计算删除后的新索引
                new_index = modification['index']
                for deletion in deletions:
                    if deletion['index'] < modification['index']:
                        new_index -= 1
                
                if new_index < len(new_data):
                    new_data[new_index]['sql'] = modification['repaired_sql']
                    stats['modified'] += 1
                    self.logger.info(f"修改SQL {new_index}: {modification['question'][:50]}...")
            
            # 写入修改后的文件
            with open(self.input_file, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ 原始文件修改完成: 修改{stats['modified']}个SQL，删除{stats['deleted']}个无效项")
            
            # 记录详细修改信息到日志文件
            await self._write_modification_log(modifications, deletions)
            
        except Exception as e:
            self.logger.error(f"修改原始JSON文件失败: {e}")
            stats['failed_modifications'] = 1
        
        return stats
    
    async def _write_modification_log(self, modifications: List[Dict], deletions: List[Dict]):
        """写入详细的修改日志"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = self.output_dir / f"file_modifications_{timestamp}.log"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"原始JSON文件修改日志\n")
                f.write(f"=" * 50 + "\n")
                f.write(f"修改时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"原始文件: {self.input_file}\n")
                f.write(f"备份文件: {str(self.input_file)}.backup\n")
                f.write(f"\n")
                
                if modifications:
                    f.write(f"修改的SQL ({len(modifications)}个):\n")
                    f.write(f"-" * 40 + "\n")
                    for i, mod in enumerate(modifications, 1):
                        f.write(f"{i}. 索引: {mod['index']}\n")
                        f.write(f"   问题: {mod['question']}\n")
                        f.write(f"   原SQL: {mod['original_sql']}\n")
                        f.write(f"   新SQL: {mod['repaired_sql']}\n\n")
                
                if deletions:
                    f.write(f"删除的无效项 ({len(deletions)}个):\n")
                    f.write(f"-" * 40 + "\n")
                    for i, del_item in enumerate(deletions, 1):
                        f.write(f"{i}. 索引: {del_item['index']}\n")
                        f.write(f"   问题: {del_item['question']}\n")
                        f.write(f"   SQL: {del_item['sql']}\n")
                        f.write(f"   错误: {del_item['error']}\n\n")
            
            self.logger.info(f"详细修改日志已保存: {log_file}")
            
        except Exception as e:
            self.logger.warning(f"写入修改日志失败: {e}")
    
    async def _repair_sqls_with_llm(self, batch_data: List[Dict]) -> List[str]:
        """
        使用LLM修复SQL批次
        
        Args:
            batch_data: 批次数据，包含question, sql, error
            
        Returns:
            修复后的SQL列表
        """
        try:
            # 构建修复提示词
            prompt = self._build_repair_prompt(batch_data)
            
            # 调用LLM
            response = await self._call_llm_for_repair(prompt)
            
            # 解析响应
            repaired_sqls = self._parse_repair_response(response, len(batch_data))
            
            return repaired_sqls
            
        except Exception as e:
            self.logger.error(f"LLM修复批次失败: {e}")
            return [""] * len(batch_data)  # 返回空字符串列表 
    
    def _build_repair_prompt(self, batch_data: List[Dict]) -> str:
        """构建SQL修复提示词"""
        
        # 提取数据库类型
        db_type = "PostgreSQL"  # 从连接字符串可以确定是PostgreSQL
        
        prompt = f"""你是一个SQL专家，专门修复PostgreSQL数据库的SQL语句错误。

数据库类型: {db_type}

请修复以下SQL语句中的错误。对于每个SQL，我会提供问题描述、错误信息和完整的SQL语句。

修复要求：
1. 只修复语法错误和表结构错误
2. 保持SQL的原始业务逻辑不变
3. 使用PostgreSQL标准语法
4. 确保修复后的SQL语法正确

需要修复的SQL：

"""
        
        # 添加每个SQL的详细信息
        for i, data in enumerate(batch_data, 1):
            prompt += f"""
{i}. 问题: {data['question']}
   错误: {data['error']}
   完整SQL:
   {data['sql']}

"""
        
        prompt += f"""
请按以下JSON格式输出修复后的SQL：
```json
{{
  "repaired_sqls": [
    "修复后的SQL1",
    "修复后的SQL2",
    "修复后的SQL3"
  ]
}}
```

注意：
- 必须输出 {len(batch_data)} 个修复后的SQL
- 如果某个SQL无法修复，请输出原始SQL
- SQL语句必须以分号结束
- 保持原始的中文别名和业务逻辑"""
        
        return prompt 
    
    async def _call_llm_for_repair(self, prompt: str) -> str:
        """调用LLM进行修复"""
        import asyncio
        
        try:
            timeout = self.config.get('llm_repair_timeout', 60)
            
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.vn.chat_with_llm,
                    question=prompt,
                    system_prompt="你是一个专业的PostgreSQL SQL专家，专门负责修复SQL语句中的语法错误和表结构错误。请严格按照JSON格式输出修复结果。"
                ),
                timeout=timeout
            )
            
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            return response.strip()
            
        except asyncio.TimeoutError:
            raise Exception(f"LLM调用超时（{timeout}秒）")
        except Exception as e:
            raise Exception(f"LLM调用失败: {e}") 
    
    def _parse_repair_response(self, response: str, expected_count: int) -> List[str]:
        """解析LLM修复响应"""
        import json
        import re
        
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有代码块，尝试直接解析
                json_str = response
            
            # 解析JSON
            parsed_data = json.loads(json_str)
            repaired_sqls = parsed_data.get('repaired_sqls', [])
            
            # 验证数量
            if len(repaired_sqls) != expected_count:
                self.logger.warning(f"LLM返回的SQL数量不匹配：期望{expected_count}，实际{len(repaired_sqls)}")
                # 补齐或截断
                while len(repaired_sqls) < expected_count:
                    repaired_sqls.append("")
                repaired_sqls = repaired_sqls[:expected_count]
            
            # 清理SQL语句
            cleaned_sqls = []
            for sql in repaired_sqls:
                if sql and isinstance(sql, str):
                    cleaned_sql = sql.strip()
                    # 确保以分号结束
                    if cleaned_sql and not cleaned_sql.endswith(';'):
                        cleaned_sql += ';'
                    cleaned_sqls.append(cleaned_sql)
                else:
                    cleaned_sqls.append("")
            
            return cleaned_sqls
            
        except json.JSONDecodeError as e:
            self.logger.error(f"解析LLM修复响应失败: {e}")
            self.logger.debug(f"原始响应: {response}")
            return [""] * expected_count
        except Exception as e:
            self.logger.error(f"处理修复响应失败: {e}")
            return [""] * expected_count 