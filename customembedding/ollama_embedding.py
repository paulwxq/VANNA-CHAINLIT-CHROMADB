import requests
import time
import numpy as np
from typing import List, Callable
from core.logging import get_vanna_logger

class OllamaEmbeddingFunction:
    def __init__(self, model_name: str, base_url: str, embedding_dimension: int):
        self.model_name = model_name
        self.base_url = base_url
        self.embedding_dimension = embedding_dimension
        self.max_retries = 3
        self.retry_interval = 2
        
        # 初始化日志
        self.logger = get_vanna_logger("OllamaEmbedding")

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
                self.logger.error(f"获取embedding时出错: {e}")
                embeddings.append([0.0] * self.embedding_dimension)
                
        return embeddings
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """为文档列表生成嵌入向量（兼容ChromaDB接口）"""
        return self.__call__(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """为单个查询文本生成嵌入向量（兼容ChromaDB接口）"""
        return self.generate_embedding(text)
    
    def generate_embedding(self, text: str) -> List[float]:
        """为单个文本生成嵌入向量"""
        self.logger.debug(f"生成Ollama嵌入向量，文本长度: {len(text)} 字符")
        
        if not text or len(text.strip()) == 0:
            self.logger.debug("输入文本为空，返回零向量")
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
                    self.logger.error(error_msg)
                    
                    if response.status_code in (429, 500, 502, 503, 504):
                        retries += 1
                        if retries <= self.max_retries:
                            wait_time = self.retry_interval * (2 ** (retries - 1))
                            self.logger.info(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                            time.sleep(wait_time)
                            continue
                    
                    raise ValueError(error_msg)
                
                result = response.json()
                
                if "embedding" in result:
                    vector = result["embedding"]
                    
                    # 验证向量维度
                    actual_dim = len(vector)
                    if actual_dim != self.embedding_dimension:
                        self.logger.debug(f"向量维度不匹配: 期望 {self.embedding_dimension}, 实际 {actual_dim}")
                        # 如果维度不匹配，可以选择截断或填充
                        if actual_dim > self.embedding_dimension:
                            vector = vector[:self.embedding_dimension]
                        else:
                            vector.extend([0.0] * (self.embedding_dimension - actual_dim))
                    
                    # 添加成功生成embedding的debug日志
                    self.logger.debug(f"✓ 成功生成Ollama embedding向量，维度: {len(vector)}")
                    return vector
                else:
                    error_msg = f"Ollama API返回格式异常: {result}"
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)
                
            except Exception as e:
                self.logger.error(f"生成Ollama embedding时出错: {str(e)}")
                retries += 1
                
                if retries <= self.max_retries:
                    wait_time = self.retry_interval * (2 ** (retries - 1))
                    self.logger.info(f"等待 {wait_time} 秒后重试 ({retries}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"已达到最大重试次数 ({self.max_retries})，生成embedding失败")
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
            self.logger.info(f"测试Ollama嵌入模型连接 - 模型: {self.model_name}")
            self.logger.info(f"Ollama服务地址: {self.base_url}")
            
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