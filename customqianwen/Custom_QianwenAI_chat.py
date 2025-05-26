import os
from openai import OpenAI
from vanna.base import VannaBase


class QianWenAI_Chat(VannaBase):
    def __init__(self, client=None, config=None):
        print("...QianWenAI_Chat init...")
        VannaBase.__init__(self, config=config)

        print("传入的 config 参数如下：")
        for key, value in self.config.items():
            print(f"  {key}: {value}")

        # default parameters - can be overrided using config
        self.temperature = 0.7

        if "temperature" in config:
            print(f"temperature is changed to: {config['temperature']}")
            self.temperature = config["temperature"]

        if "api_type" in config:
            raise Exception(
                "Passing api_type is now deprecated. Please pass an OpenAI client instead."
            )

        if "api_base" in config:
            raise Exception(
                "Passing api_base is now deprecated. Please pass an OpenAI client instead."
            )

        if "api_version" in config:
            raise Exception(
                "Passing api_version is now deprecated. Please pass an OpenAI client instead."
            )

        if client is not None:
            self.client = client
            return

        if config is None and client is None:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            return

        if "api_key" in config:
            if "base_url" not in config:
                self.client = OpenAI(api_key=config["api_key"],
                                     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
            else:
                self.client = OpenAI(api_key=config["api_key"],
                                     base_url=config["base_url"])
                
    # 生成SQL的时候，使用中文别名 - 基于VannaBase源码直接实现
    def get_sql_prompt(self, initial_prompt: str, question: str, question_sql_list: list, ddl_list: list, doc_list: list, **kwargs):
        """
        基于VannaBase源码实现，在第7点添加中文别名指令
        """
        print(f"[DEBUG] 开始生成SQL提示词，问题: {question}")
        
        if initial_prompt is None:
            initial_prompt = f"You are a {self.dialect} expert. " + \
            "Please help to generate a SQL query to answer the question. Your response should ONLY be based on the given context and follow the response guidelines and format instructions. "

        initial_prompt = self.add_ddl_to_prompt(
            initial_prompt, ddl_list, max_tokens=self.max_tokens
        )

        if self.static_documentation != "":
            doc_list.append(self.static_documentation)

        initial_prompt = self.add_documentation_to_prompt(
            initial_prompt, doc_list, max_tokens=self.max_tokens
        )

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
            "   - 包括原始字段名也要添加中文别名，例如：gender AS 性别, card_category AS 卡片类型\n"
            "   - 计算字段也要有中文别名，例如：COUNT(*) AS 持卡人数\n"
            "   - 中文别名要准确反映字段的业务含义\n"
            "   - 绝对不能有任何字段没有中文别名，这会影响表格的可读性\n"
            "   - 这样可以提高图表的可读性和用户体验\n"
            "   正确示例：SELECT gender AS 性别, card_category AS 卡片类型, COUNT(*) AS 持卡人数 FROM table_name\n"
            "   错误示例：SELECT gender, card_category AS 卡片类型, COUNT(*) AS 持卡人数 FROM table_name\n"
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
        
        print(f"[DEBUG] SQL提示词生成完成，消息数量: {len(message_log)}")
        return message_log

    # 生成图形的时候，使用中文标注
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

        # 调用父类submit_prompt方法，并清理结果
        plotly_code = self.submit_prompt(message_log, kwargs=kwargs)

        return self._sanitize_plotly_code(self._extract_python_code(plotly_code))
    
    def system_message(self, message: str) -> any:
        print(f"system_content: {message}")
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        print(f"\nuser_content: {message}")
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        print(f"assistant_content: {message}")
        return {"role": "assistant", "content": message}

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

    # def get_plotly_figure(self, plotly_code: str, df, dark_mode: bool = True):
    #     """
    #     重写父类方法，确保Flask应用也使用我们的自定义图表生成逻辑
    #     这个方法会被VannaFlaskApp调用，而不是generate_plotly_code
    #     """
    #     print(f"[DEBUG] get_plotly_figure被调用，plotly_code长度: {len(plotly_code) if plotly_code else 0}")
        
    #     # 如果没有提供plotly_code，尝试生成一个
    #     if not plotly_code or plotly_code.strip() == "":
    #         print(f"[DEBUG] plotly_code为空，尝试生成默认图表")
    #         # 生成一个简单的默认图表
    #         df_metadata = f"DataFrame形状: {df.shape}\n列名: {list(df.columns)}\n数据类型:\n{df.dtypes}"
    #         plotly_code = self.generate_plotly_code(
    #             question="数据可视化", 
    #             sql=None, 
    #             df_metadata=df_metadata
    #         )
        
    #     # 调用父类方法执行plotly代码
    #     try:
    #         return super().get_plotly_figure(plotly_code=plotly_code, df=df, dark_mode=dark_mode)
    #     except Exception as e:
    #         print(f"[ERROR] 执行plotly代码失败: {e}")
    #         print(f"[ERROR] plotly_code: {plotly_code}")
    #         # 如果执行失败，返回None或生成一个简单的备用图表
    #         return None

    def submit_prompt(self, prompt, **kwargs) -> str:
        if prompt is None:
            raise Exception("Prompt is None")

        if len(prompt) == 0:
            raise Exception("Prompt is empty")

        # Count the number of tokens in the message log
        # Use 4 as an approximation for the number of characters per token
        num_tokens = 0
        for message in prompt:
            num_tokens += len(message["content"]) / 4

        # 从配置和参数中获取enable_thinking设置
        # 优先使用参数中传入的值，如果没有则从配置中读取，默认为False
        enable_thinking = kwargs.get("enable_thinking", self.config.get("enable_thinking", False))
        
        # 公共参数
        common_params = {
            "messages": prompt,
            "stop": None,
            "temperature": self.temperature,
        }
        
        # 如果启用了thinking，则使用流式处理，但不直接传递enable_thinking参数
        if enable_thinking:
            common_params["stream"] = True
            # 千问API不接受enable_thinking作为参数，可能需要通过header或其他方式传递
            # 也可能它只是默认启用stream=True时的thinking功能
        
        model = None
        # 确定使用的模型
        if kwargs.get("model", None) is not None:
            model = kwargs.get("model", None)
            common_params["model"] = model
        elif kwargs.get("engine", None) is not None:
            engine = kwargs.get("engine", None)
            common_params["engine"] = engine
            model = engine
        elif self.config is not None and "engine" in self.config:
            common_params["engine"] = self.config["engine"]
            model = self.config["engine"]
        elif self.config is not None and "model" in self.config:
            common_params["model"] = self.config["model"]
            model = self.config["model"]
        else:
            if num_tokens > 3500:
                model = "qwen-long"
            else:
                model = "qwen-plus"
            common_params["model"] = model
        
        print(f"\nUsing model {model} for {num_tokens} tokens (approx)")
        
        if enable_thinking:
            # 流式处理模式
            print("使用流式处理模式，启用thinking功能")
            
            # 检查是否需要通过headers传递enable_thinking参数
            response_stream = self.client.chat.completions.create(**common_params)
            
            # 收集流式响应
            collected_thinking = []
            collected_content = []
            
            for chunk in response_stream:
                # 处理thinking部分
                if hasattr(chunk, 'thinking') and chunk.thinking:
                    collected_thinking.append(chunk.thinking)
                
                # 处理content部分
                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                    collected_content.append(chunk.choices[0].delta.content)
            
            # 可以在这里处理thinking的展示逻辑，如保存到日志等
            if collected_thinking:
                print("Model thinking process:", "".join(collected_thinking))
            
            # 返回完整的内容
            return "".join(collected_content)
        else:
            # 非流式处理模式
            print("使用非流式处理模式")
            response = self.client.chat.completions.create(**common_params)
            
            # Find the first response from the chatbot that has text in it (some responses may not have text)
            for choice in response.choices:
                if "text" in choice:
                    return choice.text

            # If no response with text is found, return the first response's content (which may be empty)
            return response.choices[0].message.content

    # 重写 generate_sql 方法以增加异常处理
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

    # 为了解决通过sql生成question时，question是英文的问题。
    def generate_question(self, sql: str, **kwargs) -> str:
        # 这里可以自定义提示词/逻辑
        prompt = [
            self.system_message(
                "请你根据下方SQL语句推测用户的业务提问，只返回清晰的自然语言问题，不要包含任何解释或SQL内容，也不要出现表名，问题要使用中文，并以问号结尾。"
            ),
            self.user_message(sql)
        ]
        response = self.submit_prompt(prompt, **kwargs)
        # 你也可以在这里对response做后处理
        return response
    
    # 新增：直接与LLM对话的方法
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