import os
from typing import Dict, Set, Optional
from pathlib import Path
import logging

class FileNameManager:
    """文件名管理器，处理文件命名和冲突"""
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.used_names: Set[str] = set()
        self.name_mapping: Dict[str, str] = {}  # 原始名 -> 实际文件名
        self.logger = logging.getLogger("FileNameManager")
        
        # 扫描已存在的文件
        self._scan_existing_files()
    
    def _scan_existing_files(self):
        """扫描输出目录中已存在的文件"""
        if not os.path.exists(self.output_dir):
            return
        
        for root, dirs, files in os.walk(self.output_dir):
            for file in files:
                if file.endswith(('.ddl', '.md')):
                    self.used_names.add(file)
    
    def get_safe_filename(self, schema_name: str, table_name: str, suffix: str) -> str:
        """
        生成安全的文件名，避免冲突
        
        Args:
            schema_name: Schema名称
            table_name: 表名
            suffix: 文件后缀（如 .ddl 或 _detail.md）
            
        Returns:
            安全的文件名
        """
        # 生成基础文件名
        base_name = self._generate_base_name(schema_name, table_name)
        
        # 添加后缀
        if suffix.startswith('.'):
            filename = f"{base_name}{suffix}"
        else:
            filename = f"{base_name}{suffix}"
        
        # 检查冲突并生成唯一名称
        unique_filename = self._ensure_unique_filename(filename)
        
        # 记录映射关系
        original_key = f"{schema_name}.{table_name}"
        self.name_mapping[original_key] = unique_filename
        self.used_names.add(unique_filename)
        
        return unique_filename
    
    def _generate_base_name(self, schema_name: str, table_name: str) -> str:
        """
        生成基础文件名
        
        规则:
        - public.table_name → table_name
        - schema.table_name → schema__table_name  
        - 特殊字符替换: . → __, - → _, 空格 → _
        """
        if schema_name.lower() == 'public':
            safe_name = table_name
        else:
            safe_name = f"{schema_name}__{table_name}"
        
        # 替换特殊字符
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
    
    def _ensure_unique_filename(self, filename: str) -> str:
        """确保文件名唯一性"""
        if filename not in self.used_names:
            return filename
        
        # 如果重名，添加数字后缀
        base, ext = os.path.splitext(filename)
        counter = 1
        
        while True:
            unique_name = f"{base}_{counter}{ext}"
            if unique_name not in self.used_names:
                self.logger.warning(f"文件名冲突，'{filename}' 重命名为 '{unique_name}'")
                return unique_name
            counter += 1
    
    def get_full_path(self, filename: str, subdirectory: Optional[str] = None) -> str:
        """
        获取完整文件路径
        
        Args:
            filename: 文件名
            subdirectory: 子目录（如 'ddl' 或 'docs'）
            
        Returns:
            完整路径
        """
        if subdirectory:
            full_path = os.path.join(self.output_dir, subdirectory, filename)
        else:
            full_path = os.path.join(self.output_dir, filename)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        return full_path
    
    def get_mapping_report(self) -> Dict[str, str]:
        """获取文件名映射报告"""
        return self.name_mapping.copy()
    
    def write_mapping_report(self):
        """写入文件名映射报告"""
        report_path = os.path.join(self.output_dir, "filename_mapping.txt")
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("# 文件名映射报告\n")
                f.write("# 格式: 原始表名 -> 实际文件名\n\n")
                
                for original, actual in sorted(self.name_mapping.items()):
                    f.write(f"{original} -> {actual}\n")
            
            self.logger.info(f"文件名映射报告已保存到: {report_path}")
        except Exception as e:
            self.logger.error(f"写入文件名映射报告失败: {e}")