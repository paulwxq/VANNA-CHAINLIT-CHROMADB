# 训练数据管理系统说明

## 概述

训练数据管理系统位于 `data_pipeline/trainer/` 目录下，负责将生成的训练数据文件加载到向量数据库中。该系统支持多种文件格式的自动识别和处理。

## 主要组件

### 1. 核心文件
- **`run_training.py`** - 主训练脚本，支持命令行调用
- **`vanna_trainer.py`** - 训练器核心模块，封装训练逻辑

### 2. 配置来源
训练数据路径配置现已统一到 `data_pipeline/config.py`：
```python
SCHEMA_TOOLS_CONFIG = {
    "output_directory": "./data_pipeline/training_data/",
    # 其他配置...
}
```

## 文件格式与处理逻辑

### 文件处理优先级和判断逻辑
代码按以下顺序判断文件类型：

1. **`.ddl`** → DDL文件
2. **`.md` 或 `.markdown`** → 文档文件  
3. **`_pair.json` 或 `_pairs.json`** → JSON问答对文件
4. **`_pair.sql` 或 `_pairs.sql`** → 格式化问答对文件
5. **`.sql` (但不以 `_pair.sql` 或 `_pairs.sql` 结尾)** → SQL示例文件
6. **其他** → 跳过处理

### 1. DDL文件 (`.ddl`)
- **处理函数**: `train_ddl_statements()`
- **调用的训练函数**: `train_ddl()`
- **文件格式**: 
  - 使用分号 (`;`) 作为分隔符
  - 每个DDL语句之间用分号分隔
  - 示例格式:
    ```sql
    create table public.bss_company (
      id varchar(32) not null     -- 主键ID，主键,
      version integer not null    -- 版本号,
      company_name varchar(255)   -- 公司名称,
      primary key (id)
    );
    ```

### 2. 文档文件 (`.md`, `.markdown`)
- **处理函数**: `train_documentation_blocks()`
- **调用的训练函数**: `train_documentation()`
- **文件格式**:
  - **Markdown文件**: 按标题级别自动分割 (`#`, `##`, `###`)
  - **非Markdown文件**: 使用 `---` 作为分隔符
  - 示例格式:
    ```markdown
    ## bss_company（存储高速公路管理公司信息）
    bss_company 表存储高速公路管理公司信息，用于服务区运营管理
    
    字段列表：
    - id (varchar(32)) - 主键ID [主键, 非空]
    - company_name (varchar(255)) - 公司名称
    ```

### 3. SQL示例文件 (`.sql`, 但排除 `_pair.sql` 和 `_pairs.sql`)
- **处理函数**: `train_sql_examples()`
- **调用的训练函数**: `train_sql_example()`
- **文件格式**:
  - 使用分号 (`;`) 作为分隔符
  - 每个SQL示例之间用分号分隔
  - 示例格式:
    ```sql
    SELECT * FROM bss_company WHERE delete_ts IS NULL;
    SELECT company_name, company_no FROM bss_company ORDER BY company_name;
    ```

### 4. 格式化问答对文件 (`_pair.sql`, `_pairs.sql`)
- **处理函数**: `train_formatted_question_sql_pairs()`
- **调用的训练函数**: `train_question_sql_pair()`
- **文件格式**:
  - 使用 `Question:` 和 `SQL:` 标记
  - 问答对之间用双空行分隔
  - 支持单行和多行SQL
  - 示例格式:
    ```
    Question: 查询所有公司信息
    SQL: SELECT * FROM bss_company WHERE delete_ts IS NULL;

    Question: 统计每个公司的服务区数量
    SQL: 
    SELECT c.company_name, COUNT(sa.id) as area_count
    FROM bss_company c 
    LEFT JOIN bss_service_area sa ON c.id = sa.company_id 
    WHERE c.delete_ts IS NULL
    GROUP BY c.company_name;
    ```

### 5. JSON格式问答对文件 (`_pair.json`, `_pairs.json`)
- **处理函数**: `train_json_question_sql_pairs()`
- **调用的训练函数**: `train_question_sql_pair()`
- **文件格式**:
  - 标准JSON数组格式
  - 每个对象包含 `question` 和 `sql` 字段
  - 示例格式:
    ```json
    [
        {
            "question": "查询所有公司信息",
            "sql": "SELECT * FROM bss_company WHERE delete_ts IS NULL"
        },
        {
            "question": "按公司统计服务区数量",
            "sql": "SELECT company_name, COUNT(*) FROM bss_service_area GROUP BY company_name"
        }
    ]
    ```

## 使用方式

### 1. 命令行使用

#### 基本使用
```bash
# 使用默认配置路径
python -m data_pipeline.trainer.run_training

# 指定训练数据目录
python -m data_pipeline.trainer.run_training --data_path ./data_pipeline/training_data/
```

### 2. 在工作流中调用
训练数据加载已集成到工作流编排器中，作为第4步自动执行：
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/database" \
  --table-list tables.txt \
  --business-context "业务描述"
```

### 3. 编程方式调用
```python
from data_pipeline.trainer.run_training import process_training_files

# 处理训练文件
success = process_training_files("./data_pipeline/training_data/")
if success:
    print("训练数据加载成功")
```

## 扫描策略

### 目录扫描范围
- **只扫描指定目录的直接文件**，不递归扫描子目录
- 跳过所有子目录，只处理文件

### 不支持的文件类型
- **`.txt` 文件** - 不被处理
- **其他扩展名文件** - 被跳过
- **子目录** - 被忽略

## 配置架构

### 配置优先级
```
命令行参数 > data_pipeline/config.py > 默认值
```

### 统一配置
所有数据管道相关配置现统一在 `data_pipeline/config.py`：
```python
SCHEMA_TOOLS_CONFIG = {
    "output_directory": "./data_pipeline/training_data/",
    # 训练相关配置...
}
```

## 统计信息

训练完成后显示统计：
- DDL文件数量
- 文档文件数量  
- SQL示例文件数量
- 格式化问答对文件数量
- JSON问答对文件数量
- 总训练记录数
- 各数据类型分布

## 向量数据库集成

### 支持的向量数据库
- **ChromaDB** - 本地文件存储
- **PgVector** - PostgreSQL向量扩展

### 数据类型标识
训练数据加载时会自动标记数据类型：
- `ddl` - DDL语句
- `documentation` - 文档内容
- `sql` - SQL示例和问答对

### 验证机制
训练完成后自动验证：
- 从向量数据库检索训练数据
- 统计各类型数据数量
- 确保数据成功加载

## 最佳实践

### 文件组织
```
data_pipeline/training_data/
├── *.ddl              # DDL文件
├── *_detail.md        # MD文档文件
├── qs_*_pair.json     # 问答对文件
├── filename_mapping.txt  # 文件映射
└── logs/              # 日志目录（如果需要）
```

### 命名规范
- DDL文件: `table_name.ddl` 或 `schema__table_name.ddl`
- MD文件: `table_name_detail.md` 或 `schema__table_name_detail.md`  
- JSON问答对: `qs_dbname_timestamp_pair.json`

### 性能优化
- 批处理配置现已移至 `app_config.py` 中的训练配置区域
- 单线程处理确保稳定性
- 自动识别文件格式，无需手动分类

这个训练数据管理系统为完整的数据管道提供了最后一环，确保生成的训练数据能够有效地加载到向量数据库中供AI模型使用。