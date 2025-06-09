import requests
import time
import numpy as np
from typing import List, Callable

class EmbeddingFunction:
    def __init__(self, model_name: str, api_key: str, base_url: str, embedding_dimension: int):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.embedding_dimension = embedding_dimension
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.max_retries = 2  # 设置默认的最大重试次数
        self.retry_interval = 2  # 设置默认的重试间隔秒数
        self.normalize_embeddings = True # 设置默认是否归一化

    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """
        对向量进行L2归一化
        Args:
            vector: 输入向量   
        Returns:
            List[float]: 归一化后的向量
        """

        if not vector:
            return []
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return (np.array(vector) / norm).tolist()
    

    def __call__(self, input) -> List[List[float]]:
        """
        为文本列表生成嵌入向量
        
        Args:
            input: 要嵌入的文本或文本列表
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        if not isinstance(input, list):
            input = [input]
            
        embeddings = []
        for text in input:
            payload = {
                "model": self.model_name,
                "input": text,
                "encoding_format": "float"
            }
            
            try:
                # 修复URL拼接问题
                url = self.base_url
                if not url.endswith("/embeddings"):
                    url = url.rstrip("/")  # 移除尾部斜杠，避免双斜杠
                    if not url.endswith("/v1/embeddings"):
                        url = f"{url}/embeddings"
                
                response = requests.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                
                result = response.json()
                
                if "data" in result and len(result["data"]) > 0:
                    vector = result["data"][0]["embedding"]
                    embeddings.append(vector)
                else:
                    raise ValueError(f"API返回无效: {result}")
                    
            except Exception as e:
                print(f"获取embedding时出错: {e}")
                # 使用实例的 embedding_dimension 来创建零向量
                embeddings.append([0.0] * self.embedding_dimension)
                
        return embeddings
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        为文档列表生成嵌入向量 (LangChain 接口)
        
        Args:
            texts: 要嵌入的文档列表
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        return self.__call__(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """
        为查询文本生成嵌入向量 (LangChain 接口)
        
        Args:
            text: 要嵌入的查询文本
            
        Returns:
            List[float]: 嵌入向量
        """
        return self.generate_embedding(text)
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        为单个文本生成嵌入向量
        
        Args:
            text (str): 要嵌入的文本
            
        Returns:
            List[float]: 嵌入向量
        """
        print(f"生成嵌入向量，文本长度: {len(text)} 字符")
        
        # 处理空文本
        if not text or len(text.strip()) == 0:
            print("输入文本为空，返回零向量")
            # self.embedding_dimension 在初始化时已被强制要求
            # 因此不应该为 None 或需要默认值
            if self.embedding_dimension is None:
                # 这个分支理论上不应该被执行，因为工厂函数会确保 embedding_dimension 已设置
                # 但为了健壮性，如果它意外地是 None，则抛出错误
                raise ValueError("Embedding dimension (self.embedding_dimension) 未被正确初始化。")
            return [0.0] * self.embedding_dimension
        
        # 准备请求体
        payload = {
            "model": self.model_name,
            "input": text,
            "encoding_format": "float"
        }
        
        # 添加重试机制
        retries = 0
        while retries <= self.max_retries:
            try:
                # 发送API请求
                url = self.base_url
                if not url.endswith("/embeddings"):
                    url = url.rstrip("/")  # 移除尾部斜杠，避免双斜杠
                    if not url.endswith("/v1/embeddings"):
                        url = f"{url}/embeddings"
                print(f"请求URL: {url}")
                
                response = requests.post(
                    url, 
                    json=payload, 
                    headers=self.headers,
                    timeout=30  # 设置超时时间
                )
                
                # 检查响应状态
                if response.status_code != 200:
                    error_msg = f"API请求错误: {response.status_code}, {response.text}"
                    print(error_msg)
                    
                    # 根据错误码判断是否需要重试
                    if response.status_code in (429, 500, 502, 503, 504):
                        retries += 1
                        if retries <= self.max_retries:
                            wait_time = self.retry_interval * (2 ** (retries - 1))  # 指数退避
                            print(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                            time.sleep(wait_time)
                            continue
                    
                    raise ValueError(error_msg)
                
                # 解析响应
                result = response.json()
                
                # 提取embedding向量
                if "data" in result and len(result["data"]) > 0 and "embedding" in result["data"][0]:
                    vector = result["data"][0]["embedding"]
                    
                    # 如果是首次调用且未提供维度，则自动设置
                    if self.embedding_dimension is None:
                        self.embedding_dimension = len(vector)
                        print(f"自动设置embedding维度为: {self.embedding_dimension}")
                    else:
                        # 验证向量维度
                        actual_dim = len(vector)
                        if actual_dim != self.embedding_dimension:
                            print(f"向量维度不匹配: 期望 {self.embedding_dimension}, 实际 {actual_dim}")
                    
                    # 如果需要归一化
                    if self.normalize_embeddings:
                        vector = self._normalize_vector(vector)
                    
                    print(f"成功生成embedding向量，维度: {len(vector)}")
                    return vector
                else:
                    error_msg = f"API返回格式异常: {result}"
                    print(error_msg)
                    raise ValueError(error_msg)
                
            except Exception as e:
                print(f"生成embedding时出错: {str(e)}")
                retries += 1
                
                if retries <= self.max_retries:
                    wait_time = self.retry_interval * (2 ** (retries - 1))  # 指数退避
                    print(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"已达到最大重试次数 ({self.max_retries})，生成embedding失败")
                    # 决定是返回零向量还是重新抛出异常
                    if self.embedding_dimension:
                        print(f"返回零向量 (维度: {self.embedding_dimension})")
                        return [0.0] * self.embedding_dimension
                    raise
        
        # 这里不应该到达，但为了完整性添加
        raise RuntimeError("生成embedding失败")

    def test_connection(self, test_text="测试文本") -> dict:
        """
        测试嵌入模型的连接和功能
        
        Args:
            test_text (str): 用于测试的文本
            
        Returns:
            dict: 包含测试结果的字典，包括是否成功、维度信息等
        """
        result = {
            "success": False,
            "model": self.model_name,
            "base_url": self.base_url,
            "message": "",
            "actual_dimension": None,
            "expected_dimension": self.embedding_dimension
        }
        
        try:
            print(f"测试嵌入模型连接 - 模型: {self.model_name}")
            print(f"API服务地址: {self.base_url}")
            
            # 验证配置
            if not self.api_key:
                result["message"] = "API密钥未设置或为空"
                return result
                
            if not self.base_url:
                result["message"] = "API服务地址未设置或为空"
                return result
                
            # 测试生成向量
            vector = self.generate_embedding(test_text)
            actual_dimension = len(vector)
            
            result["success"] = True
            result["actual_dimension"] = actual_dimension
            
            # 检查维度是否一致
            if actual_dimension != self.embedding_dimension:
                result["message"] = f"警告: 模型实际生成的向量维度({actual_dimension})与配置维度({self.embedding_dimension})不一致"
            else:
                result["message"] = f"连接测试成功，向量维度: {actual_dimension}"
                
            return result
            
        except Exception as e:
            result["message"] = f"连接测试失败: {str(e)}"
            return result

def test_embedding_connection() -> dict:
    """
    测试嵌入模型连接和配置是否正确
    
    Returns:
        dict: 测试结果，包括成功/失败状态、错误消息等
    """
    try:
        # 获取嵌入函数实例
        embedding_function = get_embedding_function()
        
        # 测试连接
        test_result = embedding_function.test_connection()
        
        if test_result["success"]:
            print(f"嵌入模型连接测试成功!")
            if "警告" in test_result["message"]:
                print(test_result["message"])
                print(f"建议将app_config.py中的EMBEDDING_CONFIG['embedding_dimension']修改为{test_result['actual_dimension']}")
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

def get_embedding_function():
    """
    根据当前配置创建合适的EmbeddingFunction实例
    支持API和Ollama两种提供商
    
    Returns:
        EmbeddingFunction或OllamaEmbeddingFunction: 根据配置类型返回相应的实例
        
    Raises:
        ImportError: 如果无法导入必要的模块
        ValueError: 如果配置无效
    """
    try:
        from common.utils import get_current_embedding_config, is_using_ollama_embedding
    except ImportError:
        raise ImportError("无法导入 common.utils，请确保该文件存在")
    
    # 获取当前embedding配置
    embedding_config = get_current_embedding_config()
    
    if is_using_ollama_embedding():
        # 使用Ollama Embedding
        try:
            from customollama.ollama_embedding import OllamaEmbeddingFunction
        except ImportError:
            raise ImportError("无法导入 OllamaEmbeddingFunction，请确保 customollama 包存在")
            
        return OllamaEmbeddingFunction(
            model_name=embedding_config["model_name"],
            base_url=embedding_config["base_url"],
            embedding_dimension=embedding_config["embedding_dimension"]
        )
    else:
        # 使用API Embedding
        try:
            api_key = embedding_config["api_key"]
            model_name = embedding_config["model_name"]
            base_url = embedding_config["base_url"]
            embedding_dimension = embedding_config["embedding_dimension"]
            
            if api_key is None:
                raise KeyError("API模式下 'api_key' 未设置 (可能环境变量 EMBEDDING_API_KEY 未定义)")
                
        except KeyError as e:
            raise KeyError(f"API Embedding配置中缺少必要的键或值无效：{e}")

        return EmbeddingFunction(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            embedding_dimension=embedding_dimension
        )