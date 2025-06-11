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

        # 获取 stream 参数
        stream_mode = kwargs.get("stream", self.config.get("stream", False) if self.config else False)
        
        # 获取 enable_thinking 参数
        enable_thinking = kwargs.get("enable_thinking", self.config.get("enable_thinking", False) if self.config else False)

        # DeepSeek API约束：enable_thinking=True时建议使用stream=True
        # 如果stream=False但enable_thinking=True，则忽略enable_thinking
        if enable_thinking and not stream_mode:
            print("WARNING: enable_thinking=True 不生效，因为它需要 stream=True")
            enable_thinking = False

        # 确定使用的模型
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
            # 根据 enable_thinking 选择模型
            if enable_thinking:
                model = "deepseek-reasoner"
            else:
                if num_tokens > 3500:
                    model = "deepseek-chat"
                else:
                    model = "deepseek-chat"

        # 模型兼容性提示（但不强制切换）
        if enable_thinking and model not in ["deepseek-reasoner"]:
            print(f"提示：模型 {model} 可能不支持推理功能，推理相关参数将被忽略")

        print(f"\nUsing model {model} for {num_tokens} tokens (approx)")
        print(f"Enable thinking: {enable_thinking}, Stream mode: {stream_mode}")

        # 构建 API 调用参数
        api_params = {
            "model": model,
            "messages": prompt,
            "stop": None,
            "temperature": self.temperature,
            "stream": stream_mode,
        }

        # 过滤掉自定义参数，避免传递给 API
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['model', 'engine', 'enable_thinking', 'stream']}

        # 根据模型过滤不支持的参数
        if model == "deepseek-reasoner":
            # deepseek-reasoner 不支持的参数
            unsupported_params = ['top_p', 'presence_penalty', 'frequency_penalty', 'logprobs', 'top_logprobs']
            for param in unsupported_params:
                if param in filtered_kwargs:
                    print(f"警告：deepseek-reasoner 不支持参数 {param}，已忽略")
                    filtered_kwargs.pop(param, None)
        else:
            # deepseek-chat 等其他模型，只过滤明确会导致错误的参数
            # 目前 deepseek-chat 支持大部分标准参数，暂不过滤
            pass

        # 添加其他参数
        api_params.update(filtered_kwargs)

        if stream_mode:
            # 流式处理模式
            if model == "deepseek-reasoner" and enable_thinking:
                print("使用流式处理模式，启用推理功能")
            else:
                print("使用流式处理模式，常规聊天")
            
            response_stream = self.client.chat.completions.create(**api_params)
            
            if model == "deepseek-reasoner" and enable_thinking:
                # 推理模型的流式处理
                collected_reasoning = []
                collected_content = []
                
                for chunk in response_stream:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        
                        # 收集推理内容
                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                            collected_reasoning.append(delta.reasoning_content)
                        
                        # 收集最终答案
                        if hasattr(delta, 'content') and delta.content:
                            collected_content.append(delta.content)
                
                # 可选：打印推理过程
                if collected_reasoning:
                    print("Model reasoning process:\n", "".join(collected_reasoning))
                
                return "".join(collected_content)
            else:
                # 其他模型的流式处理（如 deepseek-chat）
                collected_content = []
                for chunk in response_stream:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            collected_content.append(delta.content)
                
                return "".join(collected_content)
        else:
            # 非流式处理模式
            if model == "deepseek-reasoner" and enable_thinking:
                print("使用非流式处理模式，启用推理功能")
            else:
                print("使用非流式处理模式，常规聊天")
            
            response = self.client.chat.completions.create(**api_params)
            
            if model == "deepseek-reasoner" and enable_thinking:
                # 推理模型的非流式处理
                message = response.choices[0].message
                
                # 可选：打印推理过程
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    print("Model reasoning process:\n", message.reasoning_content)
                
                return message.content
            else:
                # 其他模型的非流式处理（如 deepseek-chat）
                return response.choices[0].message.content 