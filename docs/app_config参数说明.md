# app_config.py 参数配置说明

## 一、核心架构配置

### 1. 模型提供商选择

#### LLM模型提供商
- **`LLM_MODEL_TYPE`**: 选择大语言模型的提供商类型
  - 可选值：`"api"` 或 `"ollama"`
  - 默认值：`"api"`
  - 样例值：`"api"`
  - 依赖关系：
    - 当选择 `"api"` 时，必须设置 `API_LLM_MODEL`
    - 当选择 `"ollama"` 时，将使用 `OLLAMA_LLM_CONFIG` 配置

#### Embedding模型提供商
- **`EMBEDDING_MODEL_TYPE`**: 选择嵌入模型的提供商类型
  - 可选值：`"api"` 或 `"ollama"`
  - 默认值：`"ollama"`
  - 样例值：`"ollama"`
  - 依赖关系：
    - 当选择 `"api"` 时，使用 `API_EMBEDDING_CONFIG`
    - 当选择 `"ollama"` 时，使用 `OLLAMA_EMBEDDING_CONFIG`

#### API模型选择
- **`API_LLM_MODEL`**: 当 `LLM_MODEL_TYPE="api"` 时使用的模型
  - 可选值：`"qianwen"` 或 `"deepseek"`
  - 默认值：`"deepseek"`
  - 样例值：`"deepseek"`
  - 依赖关系：
    - 当选择 `"qianwen"` 时，使用 `API_QIANWEN_CONFIG`
    - 当选择 `"deepseek"` 时，使用 `API_DEEPSEEK_CONFIG`

#### 向量数据库选择
- **`VECTOR_DB_TYPE`**: 选择向量数据库类型
  - 可选值：`"chromadb"` 或 `"pgvector"`
  - 默认值：`"pgvector"`
  - 样例值：`"pgvector"`
  - 依赖关系：
    - 当选择 `"chromadb"` 时，使用本地文件存储
    - 当选择 `"pgvector"` 时，使用 `PGVECTOR_CONFIG` 配置

## 二、模型配置

### 1. API模型配置

#### DeepSeek模型配置 (`API_DEEPSEEK_CONFIG`)
- **`api_key`**: DeepSeek API密钥（从环境变量 `DEEPSEEK_API_KEY` 读取）
  - 样例值：`"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"`
- **`model`**: 模型版本
  - 可选值：`"deepseek-reasoner"` 或 `"deepseek-chat"`
  - 默认值：`"deepseek-reasoner"`
  - 样例值：`"deepseek-reasoner"`
- **`allow_llm_to_see_data`**: 是否允许模型查看数据
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`temperature`**: 温度参数，控制创造性
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.6`
  - 样例值：`0.6`
- **`n_results`**: 返回结果数量
  - 默认值：`6`
  - 样例值：`6`
- **`language`**: 语言设置
  - 默认值：`"Chinese"`
  - 样例值：`"Chinese"`
- **`stream`**: 是否使用流式输出
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`enable_thinking`**: 是否启用思考功能（需要 `stream=True`）
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`

#### 千问模型配置 (`API_QIANWEN_CONFIG`)
- **`api_key`**: 千问API密钥（从环境变量 `QWEN_API_KEY` 读取）
  - 样例值：`"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"`
- **`model`**: 模型版本
  - 可选值：`"qwen3-235b-a22b"`, `"qwen3-30b-a3b"`, `"qwen-plus-latest"`, `"qwen-plus"`
  - 默认值：`"qwen3-235b-a22b"`
  - 样例值：`"qwen3-235b-a22b"`
- **`allow_llm_to_see_data`**: 是否允许模型查看数据
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`temperature`**: 温度参数
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.7`
  - 样例值：`0.7`
- **`n_results`**: 返回结果数量
  - 默认值：`6`
  - 样例值：`6`
- **`language`**: 语言设置
  - 默认值：`"Chinese"`
  - 样例值：`"Chinese"`
- **`stream`**: 是否使用流式输出
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`enable_thinking`**: 是否启用思考功能（需要 `stream=True`）
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`

### 2. Ollama模型配置

#### Ollama LLM配置 (`OLLAMA_LLM_CONFIG`)
- **`base_url`**: Ollama服务地址
  - 默认值：`"http://192.168.3.204:11434"`
  - 样例值：`"http://localhost:11434"`
- **`model`**: Ollama模型名称
  - 示例：`"qwen3:32b"`, `"deepseek-r1:32b"`
  - 样例值：`"qwen3:32b"`
- **`allow_llm_to_see_data`**: 是否允许模型查看数据
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`temperature`**: 温度参数
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.7`
  - 样例值：`0.7`
- **`n_results`**: 返回结果数量
  - 默认值：`6`
  - 样例值：`6`
- **`language`**: 语言设置
  - 默认值：`"Chinese"`
  - 样例值：`"Chinese"`
- **`timeout`**: 超时时间（秒）
  - 默认值：`60`
  - 样例值：`60`
- **`stream`**: 是否使用流式输出
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`enable_thinking`**: 是否启用思考功能
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`num_ctx`**: 上下文长度（可选）
  - 默认值：`4096`
  - 样例值：`4096`
- **`num_predict`**: 预测token数量（可选）
  - 默认值：`-1`（无限制）
  - 样例值：`-1`
- **`repeat_penalty`**: 重复惩罚（可选）
  - 默认值：`1.1`
  - 样例值：`1.1`
- **`auto_check_connection`**: 是否自动检查连接（可选）
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`

#### Ollama Embedding配置 (`OLLAMA_EMBEDDING_CONFIG`)
- **`base_url`**: Ollama服务地址
  - 默认值：`"http://192.168.3.204:11434"`
  - 样例值：`"http://localhost:11434"`
- **`model_name`**: Embedding模型名称
  - 默认值：`"bge-m3:567m"`
  - 样例值：`"bge-m3:567m"`
- **`embedding_dimension`**: 向量维度
  - 默认值：`1024`
  - 样例值：`1024`

### 3. API Embedding配置 (`API_EMBEDDING_CONFIG`)
- **`model_name`**: 模型名称
  - 可选值：`"BAAI/bge-m3"`, `"text-embedding-v4"`
  - 样例值：`"BAAI/bge-m3"`
- **`api_key`**: API密钥（从环境变量 `EMBEDDING_API_KEY` 读取）
  - 样例值：`"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"`
- **`base_url`**: API基础URL（从环境变量 `EMBEDDING_BASE_URL` 读取）
  - 样例值：`"https://api.example.com/v1"`
- **`embedding_dimension`**: 向量维度
  - 默认值：`1024`
  - 样例值：`1024`

## 三、数据库配置

### 1. 业务数据库配置 (`APP_DB_CONFIG`)
- **`host`**: 数据库主机地址
  - 样例值：`"192.168.67.1"`
- **`port`**: 数据库端口
  - 样例值：`5432`
- **`dbname`**: 数据库名称
  - 样例值：`"bank_db"`
- **`user`**: 用户名（从环境变量 `APP_DB_USER` 读取）
  - 样例值：`"postgres"`
- **`password`**: 密码（从环境变量 `APP_DB_PASSWORD` 读取）
  - 样例值：`"your_password"`

### 2. 向量数据库配置

#### PgVector配置 (`PGVECTOR_CONFIG`)
- **`host`**: 数据库主机地址
  - 样例值：`"192.168.67.1"`
- **`port`**: 数据库端口
  - 样例值：`5432`
- **`dbname`**: 数据库名称
  - 样例值：`"pgvector_db"`
- **`user`**: 用户名（从环境变量 `PGVECTOR_DB_USER` 读取）
  - 样例值：`"postgres"`
- **`password`**: 密码（从环境变量 `PGVECTOR_DB_PASSWORD` 读取）
  - 样例值：`"your_password"`

## 四、训练配置

### 1. 批处理配置
- **`TRAINING_BATCH_PROCESSING_ENABLED`**: 是否启用训练数据批处理
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
- **`TRAINING_BATCH_SIZE`**: 每批处理的训练项目数量
  - 默认值：`10`
  - 样例值：`10`
- **`TRAINING_MAX_WORKERS`**: 训练批处理的最大工作线程数
  - 默认值：`4`
  - 样例值：`4`

### 2. 训练数据路径
- **`TRAINING_DATA_PATH`**: 训练数据存放路径
  - 默认值：`"./training/data"`
  - 样例值：`"./training/data"`
  - 支持格式：
    - 相对路径（以 `.` 开头）：`"./training/data"`, `"../data"`
    - 绝对路径：`"/home/user/data"`, `"C:/data"`, `"D:\\training\\data"`
    - 相对路径（不以 `.` 开头）：`"training/data"`, `"my_data"`

## 五、功能开关

### 1. 问题重写
- **`REWRITE_QUESTION_ENABLED`**: 是否启用问题重写功能
  - 可选值：`True` 或 `False`
  - 默认值：`False`
  - 样例值：`False`
  - 功能：将上下文问题合并优化

### 2. 思考过程显示
- **`DISPLAY_SUMMARY_THINKING`**: 是否在摘要中显示思考过程
  - 可选值：`True` 或 `False`
  - 默认值：`False`
  - 样例值：`False`
  - 功能：控制是否显示 `<think></think>` 标签内容

### 3. SQL错误修正
- **`ENABLE_ERROR_SQL_PROMPT`**: 是否启用SQL错误修正提示
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`

## 六、向量查询配置

### 1. 得分阈值过滤
- **`ENABLE_RESULT_VECTOR_SCORE_THRESHOLD`**: 是否启用向量查询结果得分阈值过滤
  - 可选值：`True` 或 `False`
  - 默认值：`True`
  - 样例值：`True`
  - 功能：根据相似度得分过滤查询结果

### 2. 阈值设置
- **`RESULT_VECTOR_SQL_SCORE_THRESHOLD`**: SQL相关查询阈值
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.65`
  - 样例值：`0.65`
- **`RESULT_VECTOR_DDL_SCORE_THRESHOLD`**: 数据定义语言阈值
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.5`
  - 样例值：`0.5`
- **`RESULT_VECTOR_DOC_SCORE_THRESHOLD`**: 文档查询阈值
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.5`
  - 样例值：`0.5`
- **`RESULT_VECTOR_ERROR_SQL_SCORE_THRESHOLD`**: 错误SQL修正阈值
  - 取值范围：`0.0` 到 `1.0`
  - 默认值：`0.8`
  - 样例值：`0.8`

### 3. 返回结果限制
- **`API_MAX_RETURN_ROWS`**: 接口返回查询记录的最大行数
  - 默认值：`1000`
  - 样例值：`1000`