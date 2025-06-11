import requests
import json
from typing import List, Dict, Any
from .base_llm_chat import BaseLLMChat


class OllamaChat(BaseLLMChat):
    """Ollama AI聊天实现"""
    
    def __init__(self, config=None):
        print("...OllamaChat init...")
        super().__init__(config=config)

        # Ollama特定的配置参数
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = config.get("model", "qwen2.5:7b")
        self.timeout = config.get("timeout", 60)

    def submit_prompt(self, prompt, **kwargs) -> str:
        if prompt is None:
            raise Exception("Prompt is None")

        if len(prompt) == 0:
            raise Exception("Prompt is empty")

        # 计算token数量估计
        num_tokens = 0
        for message in prompt:
            num_tokens += len(message["content"]) / 4

        # 确定使用的模型
        model = kwargs.get("model") or kwargs.get("engine") or self.config.get("model") or self.model

        print(f"\nUsing Ollama model {model} for {num_tokens} tokens (approx)")

        # 准备Ollama API请求
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        try:
            response = requests.post(
                url, 
                json=payload, 
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            return result["message"]["content"]
            
        except requests.exceptions.RequestException as e:
            print(f"Ollama API请求失败: {e}")
            raise Exception(f"Ollama API调用失败: {str(e)}")

    def test_connection(self, test_prompt="你好") -> dict:
        """测试Ollama连接"""
        result = {
            "success": False,
            "model": self.model,
            "base_url": self.base_url,
            "message": "",
        }
        
        try:
            print(f"测试Ollama连接 - 模型: {self.model}")
            print(f"Ollama服务地址: {self.base_url}")
            
            # 测试简单对话
            prompt = [self.user_message(test_prompt)]
            response = self.submit_prompt(prompt)
            
            result["success"] = True
            result["message"] = f"Ollama连接测试成功，响应: {response[:50]}..."
            
            return result
            
        except Exception as e:
            result["message"] = f"Ollama连接测试失败: {str(e)}"
            return result 