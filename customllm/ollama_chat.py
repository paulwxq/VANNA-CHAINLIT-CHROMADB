import requests
import json
import re
from typing import List, Dict, Any, Optional
from .base_llm_chat import BaseLLMChat


class OllamaChat(BaseLLMChat):
    """Ollama AI聊天实现"""
    
    def __init__(self, config=None):
        print("...OllamaChat init...")
        super().__init__(config=config)

        # Ollama特定的配置参数
        self.base_url = config.get("base_url", "http://localhost:11434") if config else "http://localhost:11434"
        self.model = config.get("model", "qwen2.5:7b") if config else "qwen2.5:7b"
        self.timeout = config.get("timeout", 60) if config else 60
        
        # Ollama 特定参数
        self.num_ctx = config.get("num_ctx", 4096) if config else 4096  # 上下文长度
        self.num_predict = config.get("num_predict", -1) if config else -1  # 预测token数量
        self.repeat_penalty = config.get("repeat_penalty", 1.1) if config else 1.1  # 重复惩罚
        
        # 验证连接
        if config and config.get("auto_check_connection", True):
            self._check_ollama_health()

    def _check_ollama_health(self) -> bool:
        """检查 Ollama 服务健康状态"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print(f"✅ Ollama 服务连接正常: {self.base_url}")
                return True
            else:
                print(f"⚠️ Ollama 服务响应异常: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Ollama 服务连接失败: {e}")
            return False

    def submit_prompt(self, prompt, **kwargs) -> str:
        if prompt is None:
            raise Exception("Prompt is None")

        if len(prompt) == 0:
            raise Exception("Prompt is empty")

        # 计算token数量估计
        num_tokens = 0
        for message in prompt:
            num_tokens += len(message["content"]) / 4

        # 获取 stream 参数
        stream_mode = kwargs.get("stream", self.config.get("stream", False) if self.config else False)
        
        # 获取 enable_thinking 参数
        enable_thinking = kwargs.get("enable_thinking", self.config.get("enable_thinking", False) if self.config else False)

        # Ollama 约束：enable_thinking=True时建议使用stream=True
        # 如果stream=False但enable_thinking=True，则忽略enable_thinking
        if enable_thinking and not stream_mode:
            print("WARNING: enable_thinking=True 不生效，因为它需要 stream=True")
            enable_thinking = False

        # 智能模型选择
        model = self._determine_model(kwargs, enable_thinking, num_tokens)

        # 检查是否为推理模型
        is_reasoning_model = self._is_reasoning_model(model)
        
        # 模型兼容性提示（但不强制切换）
        if enable_thinking and not is_reasoning_model:
            print(f"提示：模型 {model} 不是专门的推理模型，但仍会尝试启用推理功能")

        print(f"\nUsing Ollama model {model} for {num_tokens} tokens (approx)")
        print(f"Enable thinking: {enable_thinking}, Stream mode: {stream_mode}")

        # 准备Ollama API请求
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": prompt,
            "stream": stream_mode,
            "think": enable_thinking,  # Ollama API 使用 think 参数控制推理功能
            "options": self._build_options(kwargs, is_reasoning_model, enable_thinking)
        }

        try:
            if stream_mode:
                # 流式处理模式
                if enable_thinking:
                    print("使用流式处理模式，启用推理功能")
                else:
                    print("使用流式处理模式，常规聊天")
                
                return self._handle_stream_response(url, payload, enable_thinking)
            else:
                # 非流式处理模式
                if enable_thinking:
                    print("使用非流式处理模式，启用推理功能")
                else:
                    print("使用非流式处理模式，常规聊天")
                
                return self._handle_non_stream_response(url, payload, enable_thinking)
                
        except requests.exceptions.RequestException as e:
            print(f"Ollama API请求失败: {e}")
            raise Exception(f"Ollama API调用失败: {str(e)}")

    def _handle_stream_response(self, url: str, payload: dict, enable_reasoning: bool) -> str:
        """处理流式响应"""
        response = requests.post(
            url, 
            json=payload, 
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
            stream=True
        )
        response.raise_for_status()
        
        collected_content = []
        
        for line in response.iter_lines():
            if line:
                try:
                    chunk_data = json.loads(line.decode('utf-8'))
                    
                    if 'message' in chunk_data and 'content' in chunk_data['message']:
                        content = chunk_data['message']['content']
                        collected_content.append(content)
                    
                    # 检查是否完成
                    if chunk_data.get('done', False):
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        # 合并所有内容
        full_content = "".join(collected_content)
        
        # 如果启用推理功能，尝试分离推理内容和最终答案
        if enable_reasoning:
            reasoning_content, final_content = self._extract_reasoning(full_content)
            
            if reasoning_content:
                print("Model reasoning process:\n", reasoning_content)
                return final_content
        
        return full_content

    def _handle_non_stream_response(self, url: str, payload: dict, enable_reasoning: bool) -> str:
        """处理非流式响应"""
        response = requests.post(
            url, 
            json=payload, 
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["message"]["content"]
        
        if enable_reasoning:
            # 尝试分离推理内容和最终答案
            reasoning_content, final_content = self._extract_reasoning(content)
            
            if reasoning_content:
                print("Model reasoning process:\n", reasoning_content)
                return final_content
        
        return content

    def test_connection(self, test_prompt="你好") -> dict:
        """测试Ollama连接"""
        result = {
            "success": False,
            "model": self.model,
            "base_url": self.base_url,
            "message": "",
            "available_models": [],
            "ollama_version": None
        }
        
        try:
            # 检查服务健康状态
            if not self._check_ollama_health():
                result["message"] = "Ollama 服务不可用"
                return result
            
            # 获取可用模型列表
            try:
                result["available_models"] = self.list_models()
                
                # 检查目标模型是否存在
                if self.model not in result["available_models"]:
                    print(f"警告：模型 {self.model} 不存在，尝试拉取...")
                    if not self.pull_model(self.model):
                        result["message"] = f"模型 {self.model} 不存在且拉取失败"
                        return result
            except Exception as e:
                print(f"获取模型列表失败: {e}")
                result["available_models"] = [self.model]
            
            print(f"测试Ollama连接 - 模型: {self.model}")
            print(f"Ollama服务地址: {self.base_url}")
            print(f"可用模型: {', '.join(result['available_models'])}")
            
            # 测试简单对话
            prompt = [self.user_message(test_prompt)]
            response = self.submit_prompt(prompt)
            
            result["success"] = True
            result["message"] = f"Ollama连接测试成功，响应: {response[:50]}..."
            
            return result
            
        except Exception as e:
            result["message"] = f"Ollama连接测试失败: {str(e)}"
            return result

    def _determine_model(self, kwargs: dict, enable_thinking: bool, num_tokens: int) -> str:
        """智能确定使用的模型"""
        # 优先级：运行时参数 > 配置文件 > 智能选择
        if kwargs.get("model", None) is not None:
            return kwargs.get("model")
        elif kwargs.get("engine", None) is not None:
            return kwargs.get("engine")
        elif self.config is not None and "engine" in self.config:
            return self.config["engine"]
        elif self.config is not None and "model" in self.config:
            return self.config["model"]
        else:
            # 智能选择模型
            if enable_thinking:
                # 优先选择推理模型
                try:
                    available_models = self.list_models()
                    reasoning_models = [m for m in available_models if self._is_reasoning_model(m)]
                    if reasoning_models:
                        return reasoning_models[0]  # 选择第一个推理模型
                    else:
                        print("警告：未找到推理模型，使用默认模型")
                        return self.model
                except Exception as e:
                    print(f"获取模型列表时出错: {e}，使用默认模型")
                    return self.model
            else:
                # 根据 token 数量选择模型
                if num_tokens > 8000:
                    # 长文本，选择长上下文模型
                    try:
                        available_models = self.list_models()
                        long_context_models = [m for m in available_models if any(keyword in m.lower() for keyword in ['long', '32k', '128k'])]
                        if long_context_models:
                            return long_context_models[0]
                    except Exception as e:
                        print(f"获取模型列表时出错: {e}，使用默认模型")
                
                return self.model

    def _is_reasoning_model(self, model: str) -> bool:
        """检查是否为推理模型"""
        reasoning_keywords = ['r1', 'reasoning', 'think', 'cot', 'chain-of-thought']
        return any(keyword in model.lower() for keyword in reasoning_keywords)

    def _build_options(self, kwargs: dict, is_reasoning_model: bool, enable_thinking: bool = False) -> dict:
        """构建 Ollama options 参数"""
        options = {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "repeat_penalty": self.repeat_penalty,
        }

        # 过滤掉自定义参数，避免传递给 API
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['model', 'engine', 'enable_thinking', 'stream', 'timeout']}

        # 添加其他参数到 options 中
        for k, v in filtered_kwargs.items():
            options[k] = v

        # 推理功能参数调整（当启用推理功能时）
        if enable_thinking:
            # 启用推理功能时可能需要更多的预测token
            if options["num_predict"] == -1:
                options["num_predict"] = 2048
            # 降低重复惩罚，允许更多的推理重复
            options["repeat_penalty"] = min(options["repeat_penalty"], 1.05)
            # 对于推理模型，可以进一步优化参数
            if is_reasoning_model:
                # 推理模型可能需要更长的上下文
                options["num_ctx"] = max(options["num_ctx"], 8192)

        return options

    def _is_reasoning_content(self, content: str) -> bool:
        """判断内容是否为推理内容"""
        reasoning_patterns = [
            r'<think>.*?</think>',
            r'<reasoning>.*?</reasoning>',
            r'<analysis>.*?</analysis>',
            r'思考：',
            r'分析：',
            r'推理：'
        ]
        return any(re.search(pattern, content, re.DOTALL | re.IGNORECASE) for pattern in reasoning_patterns)

    def _extract_reasoning(self, content: str) -> tuple:
        """提取推理内容和最终答案"""
        reasoning_patterns = [
            r'<think>(.*?)</think>',
            r'<reasoning>(.*?)</reasoning>',
            r'<analysis>(.*?)</analysis>',
            r'思考：(.*?)(?=\n\n|\n[^思考分析推理]|$)',
            r'分析：(.*?)(?=\n\n|\n[^思考分析推理]|$)',
            r'推理：(.*?)(?=\n\n|\n[^思考分析推理]|$)'
        ]
        
        reasoning_content = ""
        final_content = content
        
        for pattern in reasoning_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)
            if matches:
                reasoning_content = "\n".join(matches)
                final_content = re.sub(pattern, '', content, flags=re.DOTALL | re.MULTILINE).strip()
                break
        
        # 如果没有找到明确的推理标记，但内容很长，尝试简单分割
        if not reasoning_content and len(content) > 500:
            lines = content.split('\n')
            if len(lines) > 10:
                # 假设前半部分是推理，后半部分是答案
                mid_point = len(lines) // 2
                potential_reasoning = '\n'.join(lines[:mid_point])
                potential_answer = '\n'.join(lines[mid_point:])
                
                # 简单启发式：如果前半部分包含推理关键词，则分离
                if any(keyword in potential_reasoning for keyword in ['思考', '分析', '推理', '因为', '所以', '首先', '然后']):
                    reasoning_content = potential_reasoning
                    final_content = potential_answer
        
        return reasoning_content, final_content

    # Ollama 独特功能
    def list_models(self) -> List[str]:
        """列出可用的模型"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)  # 使用较短的超时时间
            response.raise_for_status()
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            return models if models else [self.model]  # 如果没有模型，返回默认模型
        except requests.exceptions.RequestException as e:
            print(f"获取模型列表失败: {e}")
            return [self.model]  # 返回默认模型
        except Exception as e:
            print(f"解析模型列表失败: {e}")
            return [self.model]  # 返回默认模型

    def pull_model(self, model_name: str) -> bool:
        """拉取模型"""
        try:
            print(f"正在拉取模型: {model_name}")
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                timeout=300  # 拉取模型可能需要较长时间
            )
            response.raise_for_status()
            print(f"✅ 模型 {model_name} 拉取成功")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ 模型 {model_name} 拉取失败: {e}")
            return False

    def delete_model(self, model_name: str) -> bool:
        """删除模型"""
        try:
            response = requests.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name},
                timeout=self.timeout
            )
            response.raise_for_status()
            print(f"✅ 模型 {model_name} 删除成功")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ 模型 {model_name} 删除失败: {e}")
            return False

    def get_model_info(self, model_name: str) -> Optional[Dict]:
        """获取模型信息"""
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"获取模型信息失败: {e}")
            return None

    def get_system_info(self) -> Dict:
        """获取 Ollama 系统信息"""
        try:
            # 获取版本信息
            version_response = requests.get(f"{self.base_url}/api/version", timeout=self.timeout)
            version_info = version_response.json() if version_response.status_code == 200 else {}
            
            # 获取模型列表
            models = self.list_models()
            
            return {
                "base_url": self.base_url,
                "version": version_info.get("version", "unknown"),
                "available_models": models,
                "current_model": self.model,
                "timeout": self.timeout,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "repeat_penalty": self.repeat_penalty
            }
        except Exception as e:
            return {"error": str(e)} 