import os
import logging
from typing import List

class TableListParser:
    """表清单解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger("schema_tools.TableListParser")
    
    def parse_file(self, file_path: str) -> List[str]:
        """
        解析表清单文件
        
        Args:
            file_path: 表清单文件路径
            
        Returns:
            表名列表
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"表清单文件不存在: {file_path}")
        
        tables = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    # 移除空白字符
                    line = line.strip()
                    
                    # 跳过空行和注释行
                    if not line or line.startswith('#') or line.startswith('--'):
                        continue
                    
                    # 验证表名格式
                    if self._validate_table_name(line):
                        tables.append(line)
                        self.logger.debug(f"解析到表: {line}")
                    else:
                        self.logger.warning(f"第 {line_num} 行: 无效的表名格式: {line}")
            
            if not tables:
                raise ValueError("表清单文件中没有有效的表名")
            
            self.logger.info(f"成功解析 {len(tables)} 个表")
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
        解析表名字符串（用于测试或命令行输入）
        
        Args:
            tables_str: 表名字符串，逗号或换行分隔
            
        Returns:
            表名列表
        """
        tables = []
        
        # 支持逗号和换行分隔
        for separator in [',', '\n']:
            if separator in tables_str:
                parts = tables_str.split(separator)
                break
        else:
            parts = [tables_str]
        
        for part in parts:
            table_name = part.strip()
            if table_name and self._validate_table_name(table_name):
                tables.append(table_name)
        
        return tables