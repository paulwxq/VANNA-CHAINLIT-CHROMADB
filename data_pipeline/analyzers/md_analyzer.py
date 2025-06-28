from pathlib import Path
from typing import List, Dict, Any
from core.logging import get_data_pipeline_logger


class MDFileAnalyzer:
    """MD文件分析器"""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.logger = get_data_pipeline_logger("MDFileAnalyzer")
        
    async def read_all_md_files(self) -> str:
        """
        读取所有MD文件的完整内容
        
        Returns:
            所有MD文件内容的组合字符串
        """
        md_files = sorted(self.output_dir.glob("*_detail.md"))
        
        if not md_files:
            raise ValueError(f"在 {self.output_dir} 目录下未找到MD文件")
        
        all_contents = []
        all_contents.append(f"# 数据库表结构文档汇总\n")
        all_contents.append(f"共包含 {len(md_files)} 个表\n\n")
        
        for md_file in md_files:
            self.logger.info(f"读取MD文件: {md_file.name}")
            try:
                content = md_file.read_text(encoding='utf-8')
                
                # 添加分隔符，便于LLM区分不同表
                all_contents.append("=" * 80)
                all_contents.append(f"# 文件: {md_file.name}")
                all_contents.append("=" * 80)
                all_contents.append(content)
                all_contents.append("\n")
                
            except Exception as e:
                self.logger.error(f"读取文件 {md_file.name} 失败: {e}")
                raise
        
        combined_content = "\n".join(all_contents)
        
        # 检查内容大小（预估token数）
        estimated_tokens = len(combined_content) / 4  # 粗略估算
        if estimated_tokens > 100000:  # 假设token限制
            self.logger.warning(f"MD内容可能过大，预估tokens: {estimated_tokens:.0f}")
        
        self.logger.info(f"成功读取 {len(md_files)} 个MD文件，总字符数: {len(combined_content)}")
        
        return combined_content
    
    def get_table_summaries(self) -> List[Dict[str, str]]:
        """
        获取所有表的摘要信息
        
        Returns:
            表摘要列表
        """
        md_files = sorted(self.output_dir.glob("*_detail.md"))
        summaries = []
        
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                lines = content.split('\n')
                
                # 提取表名和描述（通常在前几行）
                table_name = ""
                description = ""
                
                for line in lines[:10]:  # 只看前10行
                    line = line.strip()
                    if line.startswith("##"):
                        # 提取表名
                        table_info = line.replace("##", "").strip()
                        if "（" in table_info:
                            table_name = table_info.split("（")[0].strip()
                        else:
                            table_name = table_info
                    elif table_name and line and not line.startswith("#"):
                        # 第一行非标题文本作为描述
                        description = line
                        break
                
                if table_name:
                    summaries.append({
                        "file": md_file.name,
                        "table_name": table_name,
                        "description": description
                    })
                    
            except Exception as e:
                self.logger.warning(f"处理文件 {md_file.name} 时出错: {e}")
        
        return summaries 