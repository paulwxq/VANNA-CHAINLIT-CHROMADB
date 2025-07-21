import os
from typing import List, Tuple
import logging

class TableListParser:
    """表清单解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger("TableListParser")
    
    def parse_file(self, file_path: str) -> List[str]:
        """
        解析表清单文件，支持换行符和逗号分隔
        
        Args:
            file_path: 表清单文件路径
            
        Returns:
            表名列表（已去重）
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"表清单文件不存在: {file_path}")
        
        tables = []
        seen_tables = set()  # 用于跟踪已见过的表名
        duplicate_count = 0  # 重复表计数
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    # 移除空白字符
                    line = line.strip()
                    
                    # 跳过空行和注释行
                    if not line or line.startswith('#') or line.startswith('--'):
                        continue
                    
                    # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
                    if ',' in line:
                        tables_in_line = [t.strip() for t in line.split(',') if t.strip()]
                    else:
                        tables_in_line = [line]
                    
                    # 验证每个表名并添加到结果中
                    for table_name in tables_in_line:
                        if self._validate_table_name(table_name):
                            # 检查是否重复
                            if table_name not in seen_tables:
                                tables.append(table_name)
                                seen_tables.add(table_name)
                                self.logger.debug(f"解析到表: {table_name}")
                            else:
                                duplicate_count += 1
                                self.logger.debug(f"第 {line_num} 行: 发现重复表名: {table_name}")
                        else:
                            self.logger.warning(f"第 {line_num} 行: 无效的表名格式: {table_name}")
            
            if not tables:
                raise ValueError("表清单文件中没有有效的表名")
            
            # 记录去重统计信息
            original_count = len(tables) + duplicate_count
            if duplicate_count > 0:
                self.logger.info(f"表清单去重统计: 原始{original_count}个表，去重后{len(tables)}个表，移除了{duplicate_count}个重复项")
            else:
                self.logger.info(f"成功解析 {len(tables)} 个表（无重复）")
            
            return tables
            
        except Exception as e:
            self.logger.error(f"解析表清单文件失败: {e}")
            raise
    
    def _validate_table_name(self, table_name: str) -> bool:
        """
        验证表名格式
        
        Args:
            table_name: 表名
            
        Returns:
            是否合法
        """
        # 基本验证：不能为空，不能包含特殊字符
        if not table_name:
            return False
        
        # 禁止的字符
        forbidden_chars = [';', '(', ')', '[', ']', '{', '}', '*', '?', '!', '@', '#', '$', '%', '^', '&']
        for char in forbidden_chars:
            if char in table_name:
                return False
        
        # 表名格式：schema.table 或 table
        parts = table_name.split('.')
        if len(parts) > 2:
            return False
        
        # 每部分都不能为空
        for part in parts:
            if not part:
                return False
        
        return True
    
    def parse_string(self, tables_str: str) -> List[str]:
        """
        解析表名字符串，支持换行符和逗号分隔（用于测试或命令行输入）
        
        Args:
            tables_str: 表名字符串，逗号或换行分隔
            
        Returns:
            表名列表（已去重）
        """
        tables = []
        seen_tables = set()
        
        # 按换行符分割，然后处理每一行
        lines = tables_str.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # 跳过空行和注释行
            if not line or line.startswith('#') or line.startswith('--'):
                continue
            
            # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
            if ',' in line:
                tables_in_line = [t.strip() for t in line.split(',') if t.strip()]
            else:
                tables_in_line = [line]
            
            # 验证每个表名并添加到结果中
            for table_name in tables_in_line:
                if table_name and self._validate_table_name(table_name):
                    if table_name not in seen_tables:
                        tables.append(table_name)
                        seen_tables.add(table_name)
        
        return tables
    
    def get_duplicate_info(self, file_path: str) -> Tuple[List[str], List[str]]:
        """
        获取表清单文件的重复信息
        
        Args:
            file_path: 表清单文件路径
            
        Returns:
            (唯一表名列表, 重复表名列表)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"表清单文件不存在: {file_path}")
        
        unique_tables = []
        duplicate_tables = []
        seen_tables = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('--'):
                        continue
                    
                    # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
                    if ',' in line:
                        tables_in_line = [t.strip() for t in line.split(',') if t.strip()]
                    else:
                        tables_in_line = [line]
                    
                    # 处理每个表名
                    for table_name in tables_in_line:
                        if self._validate_table_name(table_name):
                            if table_name not in seen_tables:
                                unique_tables.append(table_name)
                                seen_tables.add(table_name)
                            else:
                                duplicate_tables.append(table_name)
            
            return unique_tables, duplicate_tables
            
        except Exception as e:
            self.logger.error(f"获取重复信息失败: {e}")
            raise