import requests
import json
from vanna.base import VannaBase
from typing import List, Dict, Any

class OllamaChat(VannaBase):
    def __init__(self, config=None):
        print("...OllamaChat init...")
        VannaBase.__init__(self, config=config)

        print("传入的 config 参数如下：")
        for key, value in self.config.items():
            print(f"  {key}: {value}")

        # 默认参数
        self.temperature = 0.7
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = config.get("model", "qwen2.5:7b")
        self.timeout = config.get("timeout", 60)

        if "temperature" in config:
            print(f"temperature is changed to: {config['temperature']}")
            self.temperature = config["temperature"]

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

    def generate_sql(self, question: str, **kwargs) -> str:
        """重写generate_sql方法，增加异常处理"""
        try:
            print(f"[DEBUG] 尝试为问题生成SQL: {question}")
            sql = super().generate_sql(question, **kwargs)
            
            if not sql or sql.strip() == "":
                print(f"[WARNING] 生成的SQL为空")
                return None
            
            # 检查返回内容是否为有效SQL
            sql_lower = sql.lower().strip()
            error_indicators = [
                "insufficient context", "无法生成", "sorry", "cannot", "不能",
                "no relevant", "no suitable", "unable to", "无法", "抱歉"
            ]
            
            for indicator in error_indicators:
                if indicator in sql_lower:
                    print(f"[WARNING] LLM返回错误信息而非SQL: {sql}")
                    return None
            
            sql_keywords = ["select", "insert", "update", "delete", "with", "from", "where"]
            if not any(keyword in sql_lower for keyword in sql_keywords):
                print(f"[WARNING] 返回内容不像有效SQL: {sql}")
                return None
                
            print(f"[SUCCESS] 成功生成SQL: {sql}")
            return sql
            
        except Exception as e:
            print(f"[ERROR] SQL生成过程中出现异常: {str(e)}")
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
        """直接与LLM对话"""
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