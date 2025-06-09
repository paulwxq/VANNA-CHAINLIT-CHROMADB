请分析我这个项目的代码，帮我评估一个变更，我希望添加ollama的大模型。会有两种LLM，一种是推理模型，比如qwen3/deepseek，还有一种是embedding模型。
所以我现在很困惑：
1.我需要如何在app_config.py上添加配置？
2.哪些代码需要增加或重构，比如DeepSeekChat和QianWenAI_Chat，需要根据ollama的访问方式在写一个吗？
3.帮我评估当前项目要兼容ollama，需要修改哪些内容？

通过分析你的项目代码，我来帮你评估添加Ollama支持需要的变更。你的项目架构很清晰，采用了工厂模式和配置驱动的设计，这让添加Ollama支持相对简单。

## 1. 配置层面修改（app_config.py）

```python
# 在app_config.py中添加Ollama配置

# 使用的模型类型（"qwen" 或 "deepseek" 或 "ollama"）
MODEL_TYPE = "ollama"  # 新增ollama选项

# 新增：Ollama模型配置
OLLAMA_CONFIG = {
    "base_url": "http://localhost:11434",  # Ollama默认地址
    "model": "qwen2.5:7b",  # 或者其他ollama模型名称
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "timeout": 60  # ollama可能需要更长超时时间
}

# 修改：支持Ollama作为embedding模型
EMBEDDING_CONFIG = {
    "provider": "ollama",  # 新增provider字段，可选值："api", "ollama"
    "model_name": "nomic-embed-text",  # ollama embedding模型
    "api_key": os.getenv("EMBEDDING_API_KEY"),  # API方式时使用
    "base_url": "http://localhost:11434",  # ollama地址
    "embedding_dimension": 768  # 根据实际模型调整
}

# 或者分别配置API和Ollama embedding
EMBEDDING_CONFIG_API = {
    "model_name": "BAAI/bge-m3",
    "api_key": os.getenv("EMBEDDING_API_KEY"),
    "base_url": os.getenv("EMBEDDING_BASE_URL"),
    "embedding_dimension": 1024
}

EMBEDDING_CONFIG_OLLAMA = {
    "model_name": "nomic-embed-text",
    "base_url": "http://localhost:11434",
    "embedding_dimension": 768
}

# 选择使用哪种embedding
EMBEDDING_TYPE = "ollama"  # 或 "api"
EMBEDDING_CONFIG = EMBEDDING_CONFIG_OLLAMA if EMBEDDING_TYPE == "ollama" else EMBEDDING_CONFIG_API
```

## 2. 创建Ollama LLM实现

创建新文件 `customollama/ollama_chat.py`：

```python
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
```

创建 `customollama/__init__.py`：

```python
from .ollama_chat import OllamaChat
```

## 3. 修改Embedding功能

修改 `embedding_function.py`，添加Ollama支持：

```python
import requests
import time
import numpy as np
from typing import List, Callable

class OllamaEmbeddingFunction:
    def __init__(self, model_name: str, base_url: str, embedding_dimension: int):
        self.model_name = model_name
        self.base_url = base_url
        self.embedding_dimension = embedding_dimension
        self.max_retries = 2
        self.retry_interval = 2

    def __call__(self, input) -> List[List[float]]:
        """为文本列表生成嵌入向量"""
        if not isinstance(input, list):
            input = [input]
            
        embeddings = []
        for text in input:
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)
            except Exception as e:
                print(f"获取embedding时出错: {e}")
                embeddings.append([0.0] * self.embedding_dimension)
                
        return embeddings
    
    def generate_embedding(self, text: str) -> List[float]:
        """为单个文本生成嵌入向量"""
        print(f"生成Ollama嵌入向量，文本长度: {len(text)} 字符")
        
        if not text or len(text.strip()) == 0:
            print("输入文本为空，返回零向量")
            return [0.0] * self.embedding_dimension

        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model_name,
            "prompt": text
        }
        
        retries = 0
        while retries <= self.max_retries:
            try:
                response = requests.post(
                    url, 
                    json=payload,
                    timeout=30
                )
                
                if response.status_code != 200:
                    error_msg = f"Ollama API请求错误: {response.status_code}, {response.text}"
                    print(error_msg)
                    
                    if response.status_code in (429, 500, 502, 503, 504):
                        retries += 1
                        if retries <= self.max_retries:
                            wait_time = self.retry_interval * (2 ** (retries - 1))
                            print(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                            time.sleep(wait_time)
                            continue
                    
                    raise ValueError(error_msg)
                
                result = response.json()
                
                if "embedding" in result:
                    vector = result["embedding"]
                    
                    # 验证向量维度
                    actual_dim = len(vector)
                    if actual_dim != self.embedding_dimension:
                        print(f"向量维度不匹配: 期望 {self.embedding_dimension}, 实际 {actual_dim}")
                        # 如果维度不匹配，可以选择截断或填充
                        if actual_dim > self.embedding_dimension:
                            vector = vector[:self.embedding_dimension]
                        else:
                            vector.extend([0.0] * (self.embedding_dimension - actual_dim))
                    
                    print(f"成功生成Ollama embedding向量，维度: {len(vector)}")
                    return vector
                else:
                    error_msg = f"Ollama API返回格式异常: {result}"
                    print(error_msg)
                    raise ValueError(error_msg)
                
            except Exception as e:
                print(f"生成Ollama embedding时出错: {str(e)}")
                retries += 1
                
                if retries <= self.max_retries:
                    wait_time = self.retry_interval * (2 ** (retries - 1))
                    print(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"已达到最大重试次数 ({self.max_retries})，生成embedding失败")
                    return [0.0] * self.embedding_dimension
        
        raise RuntimeError("生成Ollama embedding失败")

    def test_connection(self, test_text="测试文本") -> dict:
        """测试Ollama嵌入模型的连接"""
        result = {
            "success": False,
            "model": self.model_name,
            "base_url": self.base_url,
            "message": "",
            "actual_dimension": None,
            "expected_dimension": self.embedding_dimension
        }
        
        try:
            print(f"测试Ollama嵌入模型连接 - 模型: {self.model_name}")
            print(f"Ollama服务地址: {self.base_url}")
            
            vector = self.generate_embedding(test_text)
            actual_dimension = len(vector)
            
            result["success"] = True
            result["actual_dimension"] = actual_dimension
            
            if actual_dimension != self.embedding_dimension:
                result["message"] = f"警告: 模型实际生成的向量维度({actual_dimension})与配置维度({self.embedding_dimension})不一致"
            else:
                result["message"] = f"Ollama连接测试成功，向量维度: {actual_dimension}"
                
            return result
            
        except Exception as e:
            result["message"] = f"Ollama连接测试失败: {str(e)}"
            return result

# 修改原有的get_embedding_function函数
def get_embedding_function():
    """根据配置创建合适的EmbeddingFunction实例"""
    try:
        import app_config
    except ImportError:
        raise ImportError("无法导入 app_config.py。")

    try:
        embedding_config = app_config.EMBEDDING_CONFIG
    except AttributeError:
        raise AttributeError("app_config.py 中缺少 EMBEDDING_CONFIG 配置。")

    # 检查是否使用Ollama embedding
    provider = embedding_config.get("provider", "api")
    
    if provider == "ollama":
        print("使用Ollama Embedding模型")
        return OllamaEmbeddingFunction(
            model_name=embedding_config["model_name"],
            base_url=embedding_config["base_url"],
            embedding_dimension=embedding_config["embedding_dimension"]
        )
    else:
        print("使用API Embedding模型")
        # 原有的EmbeddingFunction逻辑
        api_key = embedding_config["api_key"]
        model_name = embedding_config["model_name"]
        base_url = embedding_config["base_url"]
        embedding_dimension = embedding_config["embedding_dimension"]
        
        if api_key is None:
            raise KeyError("EMBEDDING_CONFIG 中的 'api_key' 未设置。")
            
        return EmbeddingFunction(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            embedding_dimension=embedding_dimension
        )

# 修改测试函数
def test_embedding_connection() -> dict:
    """测试嵌入模型连接"""
    try:
        embedding_function = get_embedding_function()
        test_result = embedding_function.test_connection()
        
        if test_result["success"]:
            print(f"嵌入模型连接测试成功!")
            if "警告" in test_result["message"]:
                print(test_result["message"])
        else:
            print(f"嵌入模型连接测试失败: {test_result['message']}")
            
        return test_result
        
    except Exception as e:
        error_message = f"无法测试嵌入模型连接: {str(e)}"
        print(error_message)
        return {
            "success": False,
            "message": error_message
        }
```

## 4. 修改工厂模式（vanna_llm_factory.py）

```python
"""
Vanna LLM 工厂文件，支持多种LLM提供商
"""
from vanna.chromadb import ChromaDB_VectorStore
from customqianwen.Custom_QianwenAI_chat import QianWenAI_Chat
from customdeepseek.custom_deepseek_chat import DeepSeekChat
from customollama.ollama_chat import OllamaChat  # 新增
import app_config 
from embedding_function import get_embedding_function
import os

class Vanna_Qwen_ChromaDB(ChromaDB_VectorStore, QianWenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        QianWenAI_Chat.__init__(self, config=config)

class Vanna_DeepSeek_ChromaDB(ChromaDB_VectorStore, DeepSeekChat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        DeepSeekChat.__init__(self, config=config)

# 新增Ollama支持
class Vanna_Ollama_ChromaDB(ChromaDB_VectorStore, OllamaChat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OllamaChat.__init__(self, config=config)

def create_vanna_instance(config_module=None):
    """工厂函数：创建并初始化Vanna实例"""
    if config_module is None:
        config_module = app_config

    model_type = config_module.MODEL_TYPE.lower()
    
    config = {}
    if model_type == "deepseek":
        config = config_module.API_DEEPSEEK_CONFIG.copy()
        print(f"创建DeepSeek模型实例，使用模型: {config['model']}")
        if not config.get("api_key"):
            print(f"\n错误: DeepSeek API密钥未设置或为空")
            print(f"请在.env文件中设置DEEPSEEK_API_KEY环境变量")
            import sys
            sys.exit(1)
            
    elif model_type == "qwen":
        config = config_module.API_QWEN_CONFIG.copy()
        print(f"创建Qwen模型实例，使用模型: {config['model']}")
        if not config.get("api_key"):
            print(f"\n错误: Qwen API密钥未设置或为空")
            print(f"请在.env文件中设置QWEN_API_KEY环境变量")
            import sys
            sys.exit(1)
            
    elif model_type == "ollama":  # 新增
        config = config_module.OLLAMA_CONFIG.copy()
        print(f"创建Ollama模型实例，使用模型: {config['model']}")
        print(f"Ollama服务地址: {config['base_url']}")
        # Ollama通常不需要API密钥，但可以检查服务是否可用
        try:
            import requests
            response = requests.get(f"{config['base_url']}/api/tags", timeout=5)
            if response.status_code != 200:
                print(f"警告: 无法连接到Ollama服务 ({config['base_url']})")
        except Exception as e:
            print(f"警告: Ollama服务连接测试失败: {e}")
            
    else:
        raise ValueError(f"不支持的模型类型: {model_type}") 
    
    # 获取embedding函数（支持API和Ollama两种方式）
    embedding_function = get_embedding_function()
    config["embedding_function"] = embedding_function
    
    # 打印embedding配置信息
    embedding_config = config_module.EMBEDDING_CONFIG
    provider = embedding_config.get("provider", "api")
    print(f"已配置使用 {provider.upper()} 嵌入模型: {embedding_config['model_name']}, 维度: {embedding_config['embedding_dimension']}")
    
    # 设置ChromaDB路径
    project_root = os.path.dirname(os.path.abspath(__file__))
    config["path"] = project_root
    print(f"已配置使用ChromaDB作为向量数据库，路径：{project_root}")
    
    # 创建对应的Vanna实例
    vn = None
    if model_type == "deepseek":
        vn = Vanna_DeepSeek_ChromaDB(config=config)
        print("创建DeepSeek+ChromaDB实例")
    elif model_type == "qwen":
        vn = Vanna_Qwen_ChromaDB(config=config)
        print("创建Qwen+ChromaDB实例")
    elif model_type == "ollama":  # 新增
        vn = Vanna_Ollama_ChromaDB(config=config)
        print("创建Ollama+ChromaDB实例")
    
    if vn is None:
        raise ValueError(f"未能成功创建Vanna实例，不支持的模型类型: {model_type}")

    # 连接到业务数据库
    vn.connect_to_postgres(**config_module.APP_DB_CONFIG)           
    print(f"已连接到业务数据库: "
          f"{config_module.APP_DB_CONFIG['host']}:"
          f"{config_module.APP_DB_CONFIG['port']}/"
          f"{config_module.APP_DB_CONFIG['dbname']}")
    return vn
```

## 5. 需要新增的文件结构

```
项目根目录/
├── customollama/
│   ├── __init__.py
│   └── ollama_chat.py
```

## 6. 使用示例

在你的项目中使用Ollama：

### 使用Ollama推理模型：
```python
# 在app_config.py中设置
MODEL_TYPE = "ollama"
OLLAMA_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b",  # 或其他模型
    # ... 其他配置
}
```

### 使用Ollama embedding模型：
```python
# 在app_config.py中设置
EMBEDDING_CONFIG = {
    "provider": "ollama",
    "model_name": "nomic-embed-text",
    "base_url": "http://localhost:11434",
    "embedding_dimension": 768
}
```

## 总结

通过以上修改，你的项目就可以支持Ollama了。主要变更包括：

1. **配置扩展**：在`app_config.py`中添加Ollama相关配置
2. **新增LLM实现**：创建`OllamaChat`类
3. **扩展Embedding支持**：修改`embedding_function.py`支持Ollama embedding
4. **工厂模式扩展**：在`vanna_llm_factory.py`中添加Ollama支持

这种设计保持了现有代码的兼容性，你可以通过配置轻松切换不同的LLM提供商。