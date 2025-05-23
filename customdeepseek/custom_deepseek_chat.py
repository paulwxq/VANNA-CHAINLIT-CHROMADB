import os

from openai import OpenAI
from vanna.base import VannaBase
#from base import VannaBase


# from vanna.chromadb import ChromaDB_VectorStore

# class DeepSeekVanna(ChromaDB_VectorStore, DeepSeekChat):
#     def __init__(self, config=None):
#         ChromaDB_VectorStore.__init__(self, config=config)
#         DeepSeekChat.__init__(self, config=config)

# vn = DeepSeekVanna(config={"api_key": "sk-************", "model": "deepseek-chat"})


class DeepSeekChat(VannaBase):
    def __init__(self, config=None):
        VannaBase.__init__(self, config=config)
        print("...DeepSeekChat init...")

        print("传入的 config 参数如下：")
        for key, value in self.config.items():
            print(f"  {key}: {value}")

        # default parameters
        self.temperature = 0.7

        if "temperature" in config:
            print(f"temperature is changed to: {config['temperature']}")
            self.temperature = config["temperature"]

        if config is None:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            return

        if "api_key" in config:
            if "base_url" not in config:
                self.client = OpenAI(api_key=config["api_key"], base_url="https://api.deepseek.com")
            else:
                self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    def system_message(self, message: str) -> any:
        print(f"system_content: {message}")
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        print(f"\nuser_content: {message}")
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        print(f"assistant_content: {message}")
        return {"role": "assistant", "content": message}

    def submit_prompt(self, prompt, **kwargs) -> str:
        if prompt is None:
            raise Exception("Prompt is None")

        if len(prompt) == 0:
            raise Exception("Prompt is empty")

        # Count the number of tokens in the message log
        num_tokens = 0
        for message in prompt:
            num_tokens += len(message["content"]) / 4

        model = None
        if kwargs.get("model", None) is not None:
            model = kwargs.get("model", None)
        elif kwargs.get("engine", None) is not None:
            model = kwargs.get("engine", None)
        elif self.config is not None and "engine" in self.config:
            model = self.config["engine"]
        elif self.config is not None and "model" in self.config:
            model = self.config["model"]
        else:
            if num_tokens > 3500:
                model = "deepseek-chat"
            else:
                model = "deepseek-chat"

        print(f"\nUsing model {model} for {num_tokens} tokens (approx)")

        response = self.client.chat.completions.create(
            model=model,
            messages=prompt,
            stop=None,
            temperature=self.temperature,
        )

        return response.choices[0].message.content

    def generate_sql(self, question: str, **kwargs) -> str:
        """
        重写父类的 generate_sql 方法，增加异常处理
        """
        try:
            print(f"[DEBUG] 尝试为问题生成SQL: {question}")
            # 使用父类的 generate_sql
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
        # 这里可以自定义提示词/逻辑
        prompt = [
            self.system_message(
                "请你根据下方SQL语句推测用户的业务提问，只返回清晰的自然语言问题，问题要使用中文，不要包含任何解释或SQL内容，也不要出现表名。"
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