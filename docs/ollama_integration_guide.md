# Ollama 集成使用指南

本指南介绍如何在项目中使用 Ollama 作为 LLM 和/或 Embedding 提供商。

## 概述

项目现在支持以下配置组合：

1. **全API模式**：API LLM + API Embedding
2. **全Ollama模式**：Ollama LLM + Ollama Embedding  
3. **混合模式1**：API LLM + Ollama Embedding
4. **混合模式2**：Ollama LLM + API Embedding

## 前置条件

### 安装和启动 Ollama

1. 从 [Ollama官网](https://ollama.ai) 下载并安装 Ollama
2. 启动 Ollama 服务：
   ```bash
   ollama serve
   ```
3. 拉取所需的模型：
   ```bash
   # LLM模型（选择其中一个）
   ollama pull qwen2.5:7b
   ollama pull deepseek-r1:7b
   ollama pull llama3:8b
   
   # Embedding模型
   ollama pull nomic-embed-text
   ```

## 配置说明

### 1. 基本配置参数

在 `app_config.py` 中设置以下参数：

```python
# 模型提供商类型
LLM_MODEL_TYPE = "ollama"        # "api" 或 "ollama"
EMBEDDING_MODEL_TYPE = "ollama"  # "api" 或 "ollama"

# API模式下的模型选择（Ollama模式下不使用）
API_LLM_MODEL = "qwen"           # "qwen" 或 "deepseek"

# 向量数据库类型
VECTOR_DB_TYPE = "pgvector"      # "chromadb" 或 "pgvector"
```

### 2. Ollama LLM 配置

```python
OLLAMA_LLM_CONFIG = {
    "base_url": "http://localhost:11434",  # Ollama服务地址
    "model": "qwen2.5:7b",                 # 模型名称
    "allow_llm_to_see_data": True,
    "temperature": 0.7,
    "n_results": 6,
    "language": "Chinese",
    "timeout": 60                          # 超时时间（秒）
}
```

### 3. Ollama Embedding 配置

```python
OLLAMA_EMBEDDING_CONFIG = {
    "model_name": "nomic-embed-text",      # Embedding模型名称
    "base_url": "http://localhost:11434",  # Ollama服务地址
    "embedding_dimension": 768             # 向量维度
}
```

## 使用示例

### 示例1：全Ollama模式

```python
# app_config.py
LLM_MODEL_TYPE = "ollama"
EMBEDDING_MODEL_TYPE = "ollama"
VECTOR_DB_TYPE = "chromadb"

OLLAMA_LLM_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b",
    "temperature": 0.7,
    "timeout": 60
}

OLLAMA_EMBEDDING_CONFIG = {
    "model_name": "nomic-embed-text",
    "base_url": "http://localhost:11434",
    "embedding_dimension": 768
}
```

### 示例2：混合模式（API LLM + Ollama Embedding）

```python
# app_config.py
LLM_MODEL_TYPE = "api"
EMBEDDING_MODEL_TYPE = "ollama"
API_LLM_MODEL = "qwen"
VECTOR_DB_TYPE = "pgvector"

# 使用现有的 API_QWEN_CONFIG
# 使用 OLLAMA_EMBEDDING_CONFIG
```

### 示例3：混合模式（Ollama LLM + API Embedding）

```python
# app_config.py
LLM_MODEL_TYPE = "ollama"
EMBEDDING_MODEL_TYPE = "api"
VECTOR_DB_TYPE = "chromadb"

# 使用 OLLAMA_LLM_CONFIG
# 使用现有的 API_EMBEDDING_CONFIG
```

## 代码使用

### 1. 使用工具函数检查配置

```python
from common.utils import (
    is_using_ollama_llm,
    is_using_ollama_embedding,
    get_current_model_info,
    print_current_config
)

# 检查当前配置
print_current_config()

# 检查是否使用Ollama
if is_using_ollama_llm():
    print("当前使用Ollama LLM")

if is_using_ollama_embedding():
    print("当前使用Ollama Embedding")

# 获取模型信息
model_info = get_current_model_info()
print(model_info)
```

### 2. 创建Vanna实例

```python
from vanna_llm_factory import create_vanna_instance

# 根据配置自动创建合适的实例
vn = create_vanna_instance()

# 使用实例
sql = vn.generate_sql("查询所有用户的信息")
print(sql)
```

### 3. 直接使用Ollama组件

```python
# 直接使用Ollama LLM
from customollama.ollama_chat import OllamaChat

config = {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b",
    "temperature": 0.7
}

ollama_llm = OllamaChat(config=config)
response = ollama_llm.chat_with_llm("你好")

# 直接使用Ollama Embedding
from customollama.ollama_embedding import OllamaEmbeddingFunction

embedding_func = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
    embedding_dimension=768
)

embeddings = embedding_func(["文本1", "文本2"])
```

## 测试和验证

### 1. 运行配置测试

```bash
python test_config_utils.py
```

### 2. 运行Ollama集成测试

```bash
python test_ollama_integration.py
```

### 3. 测试连接

```python
# 测试Ollama LLM连接
from customollama.ollama_chat import OllamaChat

config = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b"}
ollama_llm = OllamaChat(config=config)
result = ollama_llm.test_connection()
print(result)

# 测试Ollama Embedding连接
from customollama.ollama_embedding import OllamaEmbeddingFunction

embedding_func = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
    embedding_dimension=768
)
result = embedding_func.test_connection()
print(result)
```

## 常见问题

### 1. 连接失败

**问题**：`Ollama API调用失败: Connection refused`

**解决方案**：
- 确保Ollama服务正在运行：`ollama serve`
- 检查服务地址是否正确（默认：`http://localhost:11434`）
- 确保防火墙没有阻止连接

### 2. 模型不存在

**问题**：`model 'qwen2.5:7b' not found`

**解决方案**：
- 拉取所需模型：`ollama pull qwen2.5:7b`
- 检查可用模型：`ollama list`

### 3. 向量维度不匹配

**问题**：`向量维度不匹配: 期望 768, 实际 384`

**解决方案**：
- 更新配置中的 `embedding_dimension` 为实际维度
- 或者选择匹配的embedding模型

### 4. 超时错误

**问题**：`Ollama API调用超时`

**解决方案**：
- 增加 `timeout` 配置值
- 检查模型是否已完全加载
- 考虑使用更小的模型

## 性能优化建议

### 1. 模型选择

- **小型模型**：`qwen2.5:7b`, `llama3:8b` - 适合资源有限的环境
- **大型模型**：`qwen2.5:14b`, `deepseek-r1:32b` - 适合性能要求高的场景

### 2. 配置优化

```python
# 针对性能优化的配置
OLLAMA_LLM_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b",
    "temperature": 0.1,  # 降低随机性，提高一致性
    "timeout": 120,      # 增加超时时间
}
```

### 3. 缓存策略

- 启用向量数据库缓存
- 使用会话感知缓存
- 合理设置缓存过期时间

## 部署注意事项

### 1. 生产环境

- 确保Ollama服务的稳定性和可用性
- 配置适当的资源限制（CPU、内存、GPU）
- 设置监控和日志记录

### 2. 安全考虑

- 限制Ollama服务的网络访问
- 使用防火墙保护服务端口
- 定期更新Ollama和模型

### 3. 备份和恢复

- 备份模型文件和配置
- 准备API服务作为备用方案
- 测试故障转移流程

## 架构说明

### 统一组合类管理

项目采用了统一的组合类管理方式，所有LLM与向量数据库的组合都在 `common/vanna_combinations.py` 中定义：

```python
# 可用的组合类
from common.vanna_combinations import (
    Vanna_Qwen_ChromaDB,
    Vanna_DeepSeek_ChromaDB,
    Vanna_Ollama_ChromaDB,
    Vanna_Qwen_PGVector,
    Vanna_DeepSeek_PGVector,
    Vanna_Ollama_PGVector,
    get_vanna_class,
    print_available_combinations
)

# 动态获取组合类
cls = get_vanna_class("ollama", "chromadb")  # 返回 Vanna_Ollama_ChromaDB

# 查看所有可用组合
print_available_combinations()
```

### 工厂模式

`vanna_llm_factory.py` 使用统一的组合类文件，自动根据配置选择合适的组合：

```python
from vanna_llm_factory import create_vanna_instance

# 根据 app_config.py 中的配置自动创建实例
vn = create_vanna_instance()
```

## 测试和验证

### 1. 运行配置测试

```bash
python test_config_utils.py
```

### 2. 运行Ollama集成测试

```bash
python test_ollama_integration.py
```

### 3. 运行组合类测试

```bash
python test_vanna_combinations.py
```

## 更多资源

- [Ollama官方文档](https://ollama.ai/docs)
- [支持的模型列表](https://ollama.ai/library)
- [API参考文档](https://github.com/ollama/ollama/blob/main/docs/api.md) 