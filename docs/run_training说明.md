## 文件扩展名与处理函数对应关系

### 文件处理优先级和判断逻辑
代码中的文件类型判断按以下顺序进行：

1. **`.ddl`** → DDL文件
2. **`.md` 或 `.markdown`** → 文档文件  
3. **`_pair.json` 或 `_pairs.json`** → JSON问答对文件
4. **`_pair.sql` 或 `_pairs.sql`** → 格式化问答对文件
5. **`.sql` (但不以 `_pair.sql` 或 `_pairs.sql` 结尾)** → SQL示例文件
6. **其他** → 跳过处理

### 1. **DDL文件** (`.ddl`)
- **处理函数**: `train_ddl_statements()`
- **调用的训练函数**: `train_ddl()`
- **文件格式**: 
  - 使用分号 (`;`) 作为分隔符
  - 每个DDL语句之间用分号分隔
  - 示例格式:
    ```sql
    CREATE TABLE users (
        id INT PRIMARY KEY,
        name VARCHAR(100)
    );
    CREATE TABLE orders (
        id INT PRIMARY KEY,
        user_id INT REFERENCES users(id)
    );
    ```

### 2. **文档文件** (`.md`, `.markdown`)
- **处理函数**: `train_documentation_blocks()`
- **调用的训练函数**: `train_documentation()`
- **文件格式**:
  - **Markdown文件**: 按标题级别自动分割 (`#`, `##`, `###`)
  - **非Markdown文件**: 使用 `---` 作为分隔符
  - 示例格式:
    ```markdown
    # 用户表说明
    用户表存储系统中所有用户的基本信息...
    
    ## 字段说明
    - id: 用户唯一标识符
    - name: 用户姓名
    
    ### 注意事项
    用户名不能重复...
    ```

### 3. **SQL示例文件** (`.sql`, 但排除 `_pair.sql` 和 `_pairs.sql`)
- **处理函数**: `train_sql_examples()`
- **调用的训练函数**: `train_sql_example()`
- **文件格式**:
  - 使用分号 (`;`) 作为分隔符
  - 每个SQL示例之间用分号分隔
  - 示例格式:
    ```sql
    SELECT * FROM users WHERE age > 18;
    SELECT COUNT(*) FROM orders WHERE status = 'completed';
    SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id;
    ```

### 4. **格式化问答对文件** (`_pair.sql`, `_pairs.sql`)
- **处理函数**: `train_formatted_question_sql_pairs()`
- **调用的训练函数**: `train_question_sql_pair()`
- **文件格式**:
  - 使用 `Question:` 和 `SQL:` 标记
  - 问答对之间用双空行分隔
  - 支持单行和多行SQL
  - 示例格式:
    ```
    Question: 查询所有成年用户
    SQL: SELECT * FROM users WHERE age >= 18;

    Question: 统计每个用户的订单数量
    SQL: 
    SELECT u.name, COUNT(o.id) as order_count
    FROM users u 
    LEFT JOIN orders o ON u.id = o.user_id 
    GROUP BY u.id, u.name;
    ```

### 5. **JSON格式问答对文件** (`_pair.json`, `_pairs.json`)
- **处理函数**: `train_json_question_sql_pairs()`
- **调用的训练函数**: `train_question_sql_pair()`
- **文件格式**:
  - 标准JSON数组格式
  - 每个对象包含 `question` 和 `sql` 字段
  - 示例格式:
    ```json
    [
        {
            "question": "查询所有成年用户",
            "sql": "SELECT * FROM users WHERE age >= 18"
        },
        {
            "question": "统计每个用户的订单数量",
            "sql": "SELECT u.name, COUNT(o.id) as order_count FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id, u.name"
        }
    ]
    ```

### 6. **传统问答对文件** (其他格式，通过 `train_question_sql_pairs()` 处理)
- **处理函数**: `train_question_sql_pairs()`
- **调用的训练函数**: `train_question_sql_pair()`
- **文件格式**:
  - 每行一个问答对
  - 使用 `::` 分隔问题和SQL
  - 示例格式:
    ```
    查询所有成年用户::SELECT * FROM users WHERE age >= 18
    统计订单总数::SELECT COUNT(*) FROM orders
    ```



## 统计信息

训练完成后会显示以下统计：
- DDL文件数量
- 文档文件数量  
- SQL示例文件数量
- 格式化问答对文件数量
- JSON问答对文件数量

这个设计使得训练系统能够灵活处理多种不同格式的训练数据，满足不同场景下的数据准备需求。


# 训练脚本批处理配置
# 这些配置仅用于 training/run_training.py 训练脚本的批处理优化
# 批处理可以提高训练效率，但会增加内存使用和复杂度
# 
# TRAINING_BATCH_PROCESSING_ENABLED: 
#   - True: 启用批处理，将多个训练项目打包一起处理
#   - False: 逐项处理，每个训练项目单独处理（更稳定但较慢）
# 
# TRAINING_BATCH_SIZE: 每批处理的训练项目数量
#   - 较大值: 处理更快但占用更多内存
#   - 较小值: 内存占用少但处理较慢
#   - 建议范围: 5-20
# 
# TRAINING_MAX_WORKERS: 训练批处理的最大工作线程数
#   - 建议设置为CPU核心数的1-2倍
#   - 过多线程可能导致资源竞争
TRAINING_BATCH_PROCESSING_ENABLED = True    # 是否启用训练数据批处理
TRAINING_BATCH_SIZE = 10                    # 每批处理的训练项目数量
TRAINING_MAX_WORKERS = 4                    # 训练批处理的最大工作线程数