import os
from openai import OpenAI
from .base_llm_chat import BaseLLMChat


class DeepSeekChat(BaseLLMChat):
    """DeepSeek AI聊天实现"""
    
    def __init__(self, config=None):
        print("...DeepSeekChat init...")
        super().__init__(config=config)

        if config is None:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            return

        if "api_key" in config:
            if "base_url" not in config:
                self.client = OpenAI(api_key=config["api_key"], base_url="https://api.deepseek.com")
            else:
                self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

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

        # DeepSeek不支持thinking功能，忽略enable_thinking参数
        response = self.client.chat.completions.create(
            model=model,
            messages=prompt,
            stop=None,
            temperature=self.temperature,
        )

        return response.choices[0].message.content 