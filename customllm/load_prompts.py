"""
提示词加载器
用于从yaml文件中加载LLM提示词配置
"""
import os
import yaml
from typing import Dict, Any
from core.logging import get_vanna_logger


class PromptLoader:
    """提示词加载器类"""
    
    def __init__(self, config_path: str = None):
        """
        初始化提示词加载器
        
        Args:
            config_path: yaml配置文件路径，默认为当前目录下的llm_prompts.yaml
        """
        self.logger = get_vanna_logger("PromptLoader")
        
        if config_path is None:
            # 默认配置文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "llm_prompts.yaml")
        
        self.config_path = config_path
        self._prompts = None
        self._load_prompts()
    
    def _load_prompts(self):
        """从yaml文件加载提示词配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self._prompts = yaml.safe_load(file)
            self.logger.debug(f"成功加载提示词配置: {self.config_path}")
        except FileNotFoundError:
            self.logger.error(f"提示词配置文件未找到: {self.config_path}")
            self._prompts = {}
        except yaml.YAMLError as e:
            self.logger.error(f"解析yaml配置文件失败: {e}")
            self._prompts = {}
        except Exception as e:
            self.logger.error(f"加载提示词配置时出现未知错误: {e}")
            self._prompts = {}
    
    def get_prompt(self, category: str, key: str, **kwargs) -> str:
        """
        获取指定的提示词
        
        Args:
            category: 提示词类别 (如 'sql_generation', 'chart_generation' 等)
            key: 提示词键名 (如 'initial_prompt', 'response_guidelines' 等)
            **kwargs: 用于格式化提示词的变量
            
        Returns:
            str: 格式化后的提示词，如果找不到则返回空字符串
        """
        try:
            if category not in self._prompts:
                self.logger.warning(f"未找到提示词类别: {category}")
                return ""
            
            if key not in self._prompts[category]:
                self.logger.warning(f"未找到提示词键: {category}.{key}")
                return ""
            
            prompt_template = self._prompts[category][key]
            
            # 如果有格式化参数，进行格式化
            if kwargs:
                try:
                    return prompt_template.format(**kwargs)
                except KeyError as e:
                    self.logger.warning(f"提示词格式化失败，缺少参数: {e}")
                    return prompt_template
            
            return prompt_template
            
        except Exception as e:
            self.logger.error(f"获取提示词时出现错误: {e}")
            return ""
    
    def get_sql_initial_prompt(self, dialect: str) -> str:
        """获取SQL生成的初始提示词"""
        return self.get_prompt("sql_generation", "initial_prompt", dialect=dialect)
    
    def get_sql_response_guidelines(self, dialect: str) -> str:
        """获取SQL生成的响应指南"""
        return self.get_prompt("sql_generation", "response_guidelines", dialect=dialect)
    
    def get_chart_instructions(self) -> str:
        """获取图表生成的中文指令"""
        return self.get_prompt("chart_generation", "chinese_chart_instructions")
    
    def get_chart_system_message(self, question: str = None, sql: str = None, df_metadata: str = None) -> str:
        """获取图表生成的系统消息"""
        # 构建SQL部分
        sql_part = f"数据来源SQL查询：\n{sql}" if sql else ""
        
        # 构建问题部分
        if question:
            question_text = f"用户问题：'{question}'\n\n以下是回答用户问题的pandas DataFrame数据："
        else:
            question_text = "以下是一个pandas DataFrame数据："
        
        return self.get_prompt(
            "chart_generation", 
            "system_message_template",
            question=question_text,
            sql_part=sql_part,
            df_metadata=df_metadata or ""
        )
    
    def get_chart_user_message(self) -> str:
        """获取图表生成的用户消息"""
        chinese_instructions = self.get_chart_instructions()
        return self.get_prompt(
            "chart_generation",
            "user_message_template",
            chinese_chart_instructions=chinese_instructions
        )
    
    def get_question_generation_prompt(self) -> str:
        """获取根据SQL生成问题的提示词"""
        return self.get_prompt("question_generation", "system_prompt")
    
    def get_chat_default_prompt(self) -> str:
        """获取聊天对话的默认系统提示词"""
        return self.get_prompt("chat_with_llm", "default_system_prompt")
    
    def get_question_merge_prompt(self) -> str:
        """获取问题合并的系统提示词"""
        return self.get_prompt("question_merge", "system_prompt")
    
    def get_summary_system_message(self, question: str, df_markdown: str) -> str:
        """获取摘要生成的系统消息"""
        return self.get_prompt(
            "summary_generation",
            "system_message_template",
            question=question,
            df_markdown=df_markdown
        )
    
    def get_summary_user_instructions(self) -> str:
        """获取摘要生成的用户指令"""
        return self.get_prompt("summary_generation", "user_instructions")
    
    def reload_prompts(self):
        """重新加载提示词配置"""
        self.logger.info("重新加载提示词配置")
        self._load_prompts()


# 全局提示词加载器实例
_prompt_loader = None

def get_prompt_loader() -> PromptLoader:
    """
    获取全局提示词加载器实例（单例模式）
    
    Returns:
        PromptLoader: 提示词加载器实例
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader