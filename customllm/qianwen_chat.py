import os
from openai import OpenAI
from .base_llm_chat import BaseLLMChat


class QianWenChat(BaseLLMChat):
    """千问AI聊天实现"""
    
    def __init__(self, client=None, config=None):
        print("...QianWenChat init...")
        super().__init__(config=config)

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
        
        # 从配置和参数中获取stream设置
        # 优先级：运行时参数 > 配置文件 > 默认值(False)
        stream_mode = kwargs.get("stream", self.config.get("stream", False))
        
        # 千问API约束：enable_thinking=True时必须stream=True
        # 如果stream=False但enable_thinking=True，则忽略enable_thinking
        if enable_thinking and not stream_mode:
            print("WARNING: enable_thinking=True 不生效，因为它需要 stream=True")
            enable_thinking = False
        
        # 创建一个干净的kwargs副本，移除可能导致API错误的自定义参数
        # 注意：enable_thinking和stream是千问API的有效参数，需要正确传递
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['model', 'engine']}  # 只移除model和engine
        
        # 公共参数
        common_params = {
            "messages": prompt,
            "stop": None,
            "temperature": self.temperature,
            "stream": stream_mode,  # 明确设置stream参数
        }
        
        # 千问OpenAI兼容接口要求enable_thinking参数放在extra_body中
        if enable_thinking:
            common_params["extra_body"] = {"enable_thinking": True}
        
        # 传递其他过滤后的参数（排除enable_thinking，因为我们已经单独处理了）
        for k, v in filtered_kwargs.items():
            if k not in ['enable_thinking', 'stream']:  # 避免重复设置
                common_params[k] = v
        
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
        print(f"Enable thinking: {enable_thinking}, Stream mode: {stream_mode}")
        
        if stream_mode:
            # 流式处理模式
            if enable_thinking:
                print("使用流式处理模式，启用thinking功能")
            else:
                print("使用流式处理模式，不启用thinking功能")
            
            response_stream = self.client.chat.completions.create(**common_params)
            
            # 收集流式响应
            collected_thinking = []
            collected_content = []
            
            for chunk in response_stream:
                # 处理thinking部分（仅当enable_thinking=True时）
                if enable_thinking and hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        collected_thinking.append(delta.reasoning_content)
                
                # 处理content部分
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        collected_content.append(delta.content)
            
            # 可以在这里处理thinking的展示逻辑，如保存到日志等
            if enable_thinking and collected_thinking:
                print("Model thinking process:\n", "".join(collected_thinking))
            
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