from pathlib import Path
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass, field

from data_pipeline.utils.table_parser import TableListParser
from data_pipeline.config import SCHEMA_TOOLS_CONFIG
import logging


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    table_count: int
    ddl_count: int
    md_count: int
    error: str = ""
    missing_ddl: List[str] = field(default_factory=list)
    missing_md: List[str] = field(default_factory=list)
    duplicate_tables: List[str] = field(default_factory=list)


class FileCountValidator:
    """文件数量验证器"""
    
    def __init__(self):
        self.logger = logging.getLogger("FileCountValidator")
        self.config = SCHEMA_TOOLS_CONFIG
        
    def validate(self, table_list_file: str, output_dir: str) -> ValidationResult:
        """
        验证生成的文件数量是否与表数量一致
        
        Args:
            table_list_file: 表清单文件路径
            output_dir: 输出目录路径
            
        Returns:
            ValidationResult: 验证结果
        """
        try:
            # 1. 解析表清单获取表数量（自动去重）
            table_parser = TableListParser()
            tables = table_parser.parse_file(table_list_file)
            table_count = len(tables)
            
            # 获取重复信息
            unique_tables, duplicate_tables = table_parser.get_duplicate_info(table_list_file)
            
            # 2. 检查表数量限制
            max_tables = self.config['qs_generation']['max_tables']
            if table_count > max_tables:
                return ValidationResult(
                    is_valid=False,
                    table_count=table_count,
                    ddl_count=0,
                    md_count=0,
                    error=f"表数量({table_count})超过限制({max_tables})。请分批处理或调整配置中的max_tables参数。",
                    duplicate_tables=duplicate_tables
                )
            
            # 3. 扫描输出目录
            output_path = Path(output_dir)
            if not output_path.exists():
                return ValidationResult(
                    is_valid=False,
                    table_count=table_count,
                    ddl_count=0,
                    md_count=0,
                    error=f"输出目录不存在: {output_dir}",
                    duplicate_tables=duplicate_tables
                )
            
            # 4. 精确验证每个表对应的文件
            missing_ddl, missing_md = self._find_missing_files_precise(tables, output_path)
            
            # 计算实际存在的文件数量
            ddl_count = table_count - len(missing_ddl)
            md_count = table_count - len(missing_md)
            
            self.logger.info(f"文件统计 - 表: {table_count}, 存在DDL: {ddl_count}, 存在MD: {md_count}")
            if duplicate_tables:
                self.logger.info(f"表清单中存在 {len(duplicate_tables)} 个重复项")
            
            # 5. 验证文件完整性
            if missing_ddl or missing_md:
                error_parts = []
                if missing_ddl:
                    error_parts.append(f"缺失{len(missing_ddl)}个DDL文件")
                    self.logger.error(f"缺失的DDL文件对应的表: {', '.join(missing_ddl)}")
                
                if missing_md:
                    error_parts.append(f"缺失{len(missing_md)}个MD文件")
                    self.logger.error(f"缺失的MD文件对应的表: {', '.join(missing_md)}")
                
                return ValidationResult(
                    is_valid=False,
                    table_count=table_count,
                    ddl_count=ddl_count,
                    md_count=md_count,
                    error="; ".join(error_parts),
                    missing_ddl=missing_ddl,
                    missing_md=missing_md,
                    duplicate_tables=duplicate_tables
                )
            
            # 6. 验证通过
            self.logger.info(f"文件验证通过：{table_count}个表，{ddl_count}个DDL，{md_count}个MD")
            
            return ValidationResult(
                is_valid=True,
                table_count=table_count,
                ddl_count=ddl_count,
                md_count=md_count,
                duplicate_tables=duplicate_tables
            )
            
        except Exception as e:
            self.logger.exception("文件验证失败")
            return ValidationResult(
                is_valid=False,
                table_count=0,
                ddl_count=0,
                md_count=0,
                error=f"验证过程发生异常: {str(e)}"
            )
    
    def _find_missing_files_precise(self, tables: List[str], output_path: Path) -> Tuple[List[str], List[str]]:
        """精确查找缺失的文件，基于表名生成期望的文件名"""
        missing_ddl = []
        missing_md = []
        
        for table_spec in tables:
            # 根据FileNameManager的命名规则生成期望的文件名
            expected_filename = self._get_expected_filename(table_spec)
            
            # 检查DDL文件
            ddl_file = output_path / f"{expected_filename}.ddl"
            if not ddl_file.exists():
                missing_ddl.append(table_spec)
                self.logger.debug(f"缺失DDL文件: {ddl_file.name} (表: {table_spec})")
            
            # 检查MD文件
            md_file = output_path / f"{expected_filename}_detail.md"
            if not md_file.exists():
                missing_md.append(table_spec)
                self.logger.debug(f"缺失MD文件: {md_file.name} (表: {table_spec})")
        
        return missing_ddl, missing_md
    
    def _get_expected_filename(self, table_spec: str) -> str:
        """根据表名生成期望的文件名（复制FileNameManager的逻辑）"""
        # 解析表名
        if '.' in table_spec:
            schema, table = table_spec.split('.', 1)
        else:
            schema, table = 'public', table_spec
        
        # 生成基础文件名（遵循FileNameManager的规则）
        if schema.lower() == 'public':
            safe_name = table
        else:
            safe_name = f"{schema}__{table}"
        
        # 替换特殊字符（遵循FileNameManager的规则）
        replacements = {
            '.': '__',
            '-': '_',
            ' ': '_',
            '/': '_',
            '\\': '_',
            ':': '_',
            '*': '_',
            '?': '_',
            '"': '_',
            '<': '_',
            '>': '_',
            '|': '_'
        }
        
        for old_char, new_char in replacements.items():
            safe_name = safe_name.replace(old_char, new_char)
        
        # 移除连续的下划线
        while '__' in safe_name:
            safe_name = safe_name.replace('__', '_')
        
        return safe_name
    
    def _find_missing_files(self, tables: List[str], ddl_files: List[Path], md_files: List[Path]) -> Tuple[List[str], List[str]]:
        """查找缺失的文件"""
        # 获取已生成的文件名（不含扩展名）
        ddl_names = {f.stem for f in ddl_files}
        md_names = {f.stem.replace('_detail', '') for f in md_files}  # 移除_detail后缀
        
        missing_ddl = []
        missing_md = []
        
        # 为每个表建立可能的文件名映射
        table_to_filenames = self._get_table_filename_mapping(tables)
        
        # 检查每个表的文件
        for table_spec in tables:
            # 获取该表可能的文件名
            possible_filenames = table_to_filenames[table_spec]
            
            # 检查DDL文件
            ddl_exists = any(fname in ddl_names for fname in possible_filenames)
            if not ddl_exists:
                missing_ddl.append(table_spec)
                
            # 检查MD文件
            md_exists = any(fname in md_names for fname in possible_filenames)
            if not md_exists:
                missing_md.append(table_spec)
        
        return missing_ddl, missing_md
    
    def _get_table_filename_mapping(self, tables: List[str]) -> Dict[str, Set[str]]:
        """获取表名到可能的文件名的映射"""
        mapping = {}
        
        for table_spec in tables:
            # 解析表名
            if '.' in table_spec:
                schema, table = table_spec.split('.', 1)
            else:
                schema, table = 'public', table_spec
            
            # 生成可能的文件名
            possible_names = set()
            
            # 基本格式
            if schema.lower() == 'public':
                possible_names.add(table)
            else:
                possible_names.add(f"{schema}__{table}")
                possible_names.add(f"{schema}_{table}")  # 兼容不同格式
            
            # 考虑特殊字符替换
            safe_name = table.replace('-', '_').replace(' ', '_')
            if safe_name != table:
                if schema.lower() == 'public':
                    possible_names.add(safe_name)
                else:
                    possible_names.add(f"{schema}__{safe_name}")
                    possible_names.add(f"{schema}_{safe_name}")
            
            mapping[table_spec] = possible_names
        
        return mapping 