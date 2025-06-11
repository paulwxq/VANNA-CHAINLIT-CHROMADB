import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from vanna.base import VannaBase
# 导入配置参数
from app_config import REWRITE_QUESTION_ENABLED


class BaseLLMChat(VannaBase, ABC):
    """自定义LLM聊天基类，包含公共方法"""
    
    def __init__(self, config=None):
        VannaBase.__init__(self, config=config)
        
        print("传入的 config 参数如下：")
        for key, value in self.config.items():
            print(f"  {key}: {value}")
        
        # 默认参数
        self.temperature = 0.7
        
        if "temperature" in config:
            print(f"temperature is changed to: {config['temperature']}")
            self.temperature = config["temperature"]
        
        # 加载错误SQL提示配置
        self.enable_error_sql_prompt = self._load_error_sql_prompt_config()

    def _load_error_sql_prompt_config(self) -> bool:
        """从app_config.py加载错误SQL提示配置"""
        try:
            import app_config
            enable_error_sql = getattr(app_config, 'ENABLE_ERROR_SQL_PROMPT', False)
            print(f"[DEBUG] 错误SQL提示配置: ENABLE_ERROR_SQL_PROMPT = {enable_error_sql}")
            return enable_error_sql
        except (ImportError, AttributeError) as e:
            print(f"[WARNING] 无法加载错误SQL提示配置: {e}，使用默认值 False")
            return False

    def system_message(self, message: str) -> dict:
        """创建系统消息格式"""
        print(f"system_content: {message}")
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> dict:
        """创建用户消息格式"""
        print(f"\nuser_content: {message}")
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> dict:
        """创建助手消息格式"""
        print(f"assistant_content: {message}")
        return {"role": "assistant", "content": message}

    def get_sql_prompt(self, initial_prompt: str, question: str, question_sql_list: list, ddl_list: list, doc_list: list, **kwargs):
        """
        基于VannaBase源码实现，在第7点添加中文别名指令
        """
        print(f"[DEBUG] 开始生成SQL提示词，问题: {question}")
        
        if initial_prompt is None:
            initial_prompt = f"You are a {self.dialect} expert. " + \
            "Please help to generate a SQL query to answer the question. Your response should ONLY be based on the given context and follow the response guidelines and format instructions. "

        # 提取DDL内容（适配新的字典格式）
        ddl_content_list = []
        if ddl_list:
            for item in ddl_list:
                if isinstance(item, dict) and "content" in item:
                    ddl_content_list.append(item["content"])
                elif isinstance(item, str):
                    ddl_content_list.append(item)
        
        initial_prompt = self.add_ddl_to_prompt(
            initial_prompt, ddl_content_list, max_tokens=self.max_tokens
        )

        # 提取文档内容（适配新的字典格式）
        doc_content_list = []
        if doc_list:
            for item in doc_list:
                if isinstance(item, dict) and "content" in item:
                    doc_content_list.append(item["content"])
                elif isinstance(item, str):
                    doc_content_list.append(item)
        
        if self.static_documentation != "":
            doc_content_list.append(self.static_documentation)

        initial_prompt = self.add_documentation_to_prompt(
            initial_prompt, doc_content_list, max_tokens=self.max_tokens
        )

        # 新增：添加错误SQL示例作为负面示例（放在Response Guidelines之前）
        if self.enable_error_sql_prompt:
            try:
                error_sql_list = self.get_related_error_sql(question, **kwargs)
                if error_sql_list:
                    print(f"[DEBUG] 找到 {len(error_sql_list)} 个相关的错误SQL示例")
                    
                    # 构建格式化的负面提示内容
                    negative_prompt_content = "===Negative Examples\n"
                    negative_prompt_content += "下面是错误的SQL示例，请分析这些错误SQL的问题所在，并在生成新SQL时避免类似错误：\n\n"
                    
                    for i, error_example in enumerate(error_sql_list, 1):
                        if "question" in error_example and "sql" in error_example:
                            similarity = error_example.get('similarity', 'N/A')
                            print(f"[DEBUG] 错误SQL示例 {i}: 相似度={similarity}")
                            negative_prompt_content += f"问题: {error_example['question']}\n"
                            negative_prompt_content += f"错误的SQL: {error_example['sql']}\n\n"
                    
                    # 将负面提示添加到初始提示中
                    initial_prompt += negative_prompt_content
                else:
                    print("[DEBUG] 未找到相关的错误SQL示例")
            except Exception as e:
                print(f"[WARNING] 获取错误SQL示例失败: {e}")

        initial_prompt += (
            "===Response Guidelines \n"
            "1. If the provided context is sufficient, please generate a valid SQL query without any explanations for the question. \n"
            "2. If the provided context is almost sufficient but requires knowledge of a specific string in a particular column, please generate an intermediate SQL query to find the distinct strings in that column. Prepend the query with a comment saying intermediate_sql \n"
            "3. If the provided context is insufficient, please explain why it can't be generated. \n"
            "4. Please use the most relevant table(s). \n"
            "5. If the question has been asked and answered before, please repeat the answer exactly as it was given before. \n"
            f"6. Ensure that the output SQL is {self.dialect}-compliant and executable, and free of syntax errors. \n"
            "7. 【重要】请在SQL查询中为所有SELECT的列都使用中文别名：\n"
            "   - 每个列都必须使用 AS 中文别名 的格式，没有例外\n"
            "   - 包括原始字段名也要添加中文别名，例如：SELECT gender AS 性别, card_category AS 卡片类型\n"
            "   - 计算字段也要有中文别名，例如：SELECT COUNT(*) AS 持卡人数\n"
            "   - 中文别名要准确反映字段的业务含义"
        )

        message_log = [self.system_message(initial_prompt)]

        for example in question_sql_list:
            if example is None:
                print("example is None")
            else:
                if example is not None and "question" in example and "sql" in example:
                    message_log.append(self.user_message(example["question"]))
                    message_log.append(self.assistant_message(example["sql"]))

        message_log.append(self.user_message(question))
        
        return message_log

    def generate_plotly_code(self, question: str = None, sql: str = None, df_metadata: str = None, **kwargs) -> str:
        """
        重写父类方法，添加明确的中文图表指令
        """
        # 构建更智能的中文图表指令，根据问题和数据内容生成有意义的标签
        chinese_chart_instructions = (
            "使用中文创建图表，要求：\n"
            "1. 根据用户问题和数据内容，为图表生成有意义的中文标题\n"
            "2. 根据数据列的实际含义，为X轴和Y轴生成准确的中文标签\n"
            "3. 如果有图例，确保图例标签使用中文\n"
            "4. 所有文本（包括标题、轴标签、图例、数据标签等）都必须使用中文\n"
            "5. 标题应该简洁明了地概括图表要展示的内容\n"
            "6. 轴标签应该准确反映对应数据列的业务含义\n"
            "7. 选择最适合数据特点的图表类型（柱状图、折线图、饼图等）"
        )

        # 构建父类方法要求的message_log
        system_msg_parts = []

        if question:
            system_msg_parts.append(
                f"用户问题：'{question}'"
            )
            system_msg_parts.append(
                f"以下是回答用户问题的pandas DataFrame数据："
            )
        else:
            system_msg_parts.append("以下是一个pandas DataFrame数据：")

        if sql:
            system_msg_parts.append(f"数据来源SQL查询：\n{sql}")

        system_msg_parts.append(f"DataFrame结构信息：\n{df_metadata}")

        system_msg = "\n\n".join(system_msg_parts)

        # 构建更详细的用户消息，强调中文标签的重要性
        user_msg = (
            "请为这个DataFrame生成Python Plotly可视化代码。要求：\n\n"
            "1. 假设数据存储在名为'df'的pandas DataFrame中\n"
            "2. 如果DataFrame只有一个值，使用Indicator图表\n"
            "3. 只返回Python代码，不要任何解释\n"
            "4. 代码必须可以直接运行\n\n"
            f"{chinese_chart_instructions}\n\n"
            "特别注意：\n"
            "- 不要使用'图表标题'、'X轴标签'、'Y轴标签'这样的通用标签\n"
            "- 要根据实际数据内容和用户问题生成具体、有意义的中文标签\n"
            "- 例如：如果是性别统计，X轴可能是'性别'，Y轴可能是'人数'或'占比'\n"
            "- 标题应该概括图表的主要内容，如'男女持卡比例分布'\n\n"
            "数据标签和悬停信息要求：\n"
            "- 不要使用%{text}这样的占位符变量\n"
            "- 使用具体的数据值和中文单位，例如：text=df['列名'].astype(str) + '人'\n"
            "- 悬停信息要清晰易懂，使用中文描述\n"
            "- 确保所有显示的文本都是实际的数据值，不是变量占位符"
        )

        message_log = [
            self.system_message(system_msg),
            self.user_message(user_msg),
        ]

        # 调用submit_prompt方法，并清理结果
        plotly_code = self.submit_prompt(message_log, **kwargs)

        return self._sanitize_plotly_code(self._extract_python_code(plotly_code))

    def _extract_python_code(self, response: str) -> str:
        """从LLM响应中提取Python代码"""
        if not response:
            return ""
        
        # 查找代码块
        import re
        
        # 匹配 ```python 或 ``` 代码块
        code_pattern = r'```(?:python)?\s*(.*?)```'
        matches = re.findall(code_pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # 如果没有找到代码块，返回原始响应
        return response.strip()

    def _sanitize_plotly_code(self, code: str) -> str:
        """清理和验证Plotly代码"""
        if not code:
            return ""
        
        # 基本的代码清理
        lines = code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 移除空行和注释行
            line = line.strip()
            if line and not line.startswith('#'):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def should_generate_chart(self, df) -> bool:
        """
        判断是否应该生成图表
        对于Flask应用，这个方法决定了前端是否显示图表生成按钮
        """
        if df is None or df.empty:
            print(f"[DEBUG] should_generate_chart: df为空，返回False")
            return False
        
        # 如果数据有多行或多列，通常适合生成图表
        result = len(df) > 1 or len(df.columns) > 1
        print(f"[DEBUG] should_generate_chart: df.shape={df.shape}, 返回{result}")
        
        if result:
            return True
        
        return False

    def generate_sql(self, question: str, **kwargs) -> str:
        """
        重写父类的 generate_sql 方法，增加异常处理
        """
        try:
            print(f"[DEBUG] 尝试为问题生成SQL: {question}")
            # 调用父类的 generate_sql
            sql = super().generate_sql(question, **kwargs)
            
            if not sql or sql.strip() == "":
                print(f"[WARNING] 生成的SQL为空")
                return None
            
            # 替换 "\_" 为 "_"，解决特殊字符转义问题
            sql = sql.replace("\\_", "_")
            
            # 检查返回内容是否为有效SQL或错误信息
            sql_lower = sql.lower().strip()
            
            # 检查是否包含错误提示信息
            error_indicators = [
                "insufficient context", "无法生成", "sorry", "cannot", "不能",
                "no relevant", "no suitable", "unable to", "无法", "抱歉",
                "i don't have", "i cannot", "没有相关", "找不到", "不存在"
            ]
            
            for indicator in error_indicators:
                if indicator in sql_lower:
                    print(f"[WARNING] LLM返回错误信息而非SQL: {sql}")
                    return None
            
            # 简单检查是否像SQL语句（至少包含一些SQL关键词）
            sql_keywords = ["select", "insert", "update", "delete", "with", "from", "where"]
            if not any(keyword in sql_lower for keyword in sql_keywords):
                print(f"[WARNING] 返回内容不像有效SQL: {sql}")
                return None
                
            print(f"[SUCCESS] 成功生成SQL: {sql}")
            return sql
            
        except Exception as e:
            print(f"[ERROR] SQL生成过程中出现异常: {str(e)}")
            print(f"[ERROR] 异常类型: {type(e).__name__}")
            # 导入traceback以获取详细错误信息
            import traceback
            print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
            # 返回 None 而不是抛出异常
            return None

    def generate_question(self, sql: str, **kwargs) -> str:
        """根据SQL生成中文问题"""
        prompt = [
            self.system_message(
                "请你根据下方SQL语句推测用户的业务提问，只返回清晰的自然语言问题，不要包含任何解释或SQL内容，也不要出现表名，问题要使用中文，并以问号结尾。"
            ),
            self.user_message(sql)
        ]
        response = self.submit_prompt(prompt, **kwargs)
        return response

    def chat_with_llm(self, question: str, **kwargs) -> str:
        """
        直接与LLM对话，不涉及SQL生成
        """
        try:
            prompt = [
                self.system_message(
                    "你是一个友好的AI助手。如果用户询问的是数据库相关问题，请建议他们重新表述问题以便进行SQL查询。对于其他问题，请尽力提供有帮助的回答。"
                ),
                self.user_message(question)
            ]
            response = self.submit_prompt(prompt, **kwargs)
            return response
        except Exception as e:
            print(f"[ERROR] LLM对话失败: {str(e)}")
            return f"抱歉，我暂时无法回答您的问题。请稍后再试。"

    def generate_rewritten_question(self, last_question: str, new_question: str, **kwargs) -> str:
        """
        重写问题合并方法，通过配置参数控制是否启用合并功能
        
        Args:
            last_question (str): 上一个问题
            new_question (str): 新问题
            **kwargs: 其他参数
            
        Returns:
            str: 如果启用合并且问题相关则返回合并后的问题，否则返回新问题
        """
        # 如果未启用合并功能或没有上一个问题，直接返回新问题
        if not REWRITE_QUESTION_ENABLED or last_question is None:
            print(f"[DEBUG] 问题合并功能{'未启用' if not REWRITE_QUESTION_ENABLED else '上一个问题为空'}，直接返回新问题")
            return new_question
        
        print(f"[DEBUG] 启用问题合并功能，尝试合并问题")
        print(f"[DEBUG] 上一个问题: {last_question}")
        print(f"[DEBUG] 新问题: {new_question}")
        
        try:
            prompt = [
                self.system_message(
                    "你的目标是将一系列相关的问题合并成一个单一的问题。如果第二个问题与第一个问题无关且完全独立，则返回第二个问题。"
                    "只返回新的合并问题，不要添加任何额外的解释。该问题理论上应该能够用一个SQL语句来回答。"
                    "请用中文回答。"
                ),
                self.user_message(f"第一个问题: {last_question}\n第二个问题: {new_question}")
            ]
            
            rewritten_question = self.submit_prompt(prompt=prompt, **kwargs)
            print(f"[DEBUG] 合并后的问题: {rewritten_question}")
            return rewritten_question
            
        except Exception as e:
            print(f"[ERROR] 问题合并失败: {str(e)}")
            # 如果合并失败，返回新问题
            return new_question

    @abstractmethod
    def submit_prompt(self, prompt, **kwargs) -> str:
        """
        子类必须实现的核心提交方法
        
        Args:
            prompt: 消息列表
            **kwargs: 其他参数
            
        Returns:
            str: LLM的响应
        """
        pass 