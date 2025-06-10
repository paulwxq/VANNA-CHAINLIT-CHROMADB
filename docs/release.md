1.增加了开关 REWRITE_QUESTION_ENABLED = False，用于控制是否启用问题重写功能，也就是上下文问题合并。
"I interpreted your question as"


2.增加了开关 ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True，用于控制是否启用向量查询结果得分阈值过滤。

# 是否启用向量查询结果得分阈值过滤
# result = max((n + 1) // 2, 1)
ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True
# 向量查询结果得分阈值
RESULT_VECTOR_SQL_SCORE_THRESHOLD = 0.65
RESULT_VECTOR_DDL_SCORE_THRESHOLD = 0.5
RESULT_VECTOR_DOC_SCORE_THRESHOLD = 0.5


3.增加了错误SQL负面示例提示功能，用于提高SQL生成质量。

## 功能概述
通过向LLM提供相关的错误SQL示例作为负面示例，帮助LLM避免生成类似的错误SQL，从而提高SQL生成的准确性和质量。

## 配置参数
```python
# 是否启用错误SQL提示功能
ENABLE_ERROR_SQL_PROMPT = True

# 错误SQL相似度阈值（仅返回相似度高于此阈值的错误SQL示例）
RESULT_VECTOR_ERROR_SQL_SCORE_THRESHOLD = 0.5
```

## 实现细节

### 1. 数据存储
- 在PgVector数据库中新增 `error_sql` 集合，用于存储错误的question-sql对
- 错误SQL数据格式：`{"question": "用户问题", "sql": "错误的SQL", "type": "error_sql"}`
- 支持通过训练接口添加错误SQL示例

### 2. 向量查询
- 新增 `get_related_error_sql()` 方法，基于问题相似度查找相关的错误SQL示例
- 使用与其他向量查询一致的相似度计算和阈值过滤机制
- 错误SQL的阈值过滤逻辑：严格按阈值过滤，不设置最低返回数量

### 3. 提示词集成
- 在SQL生成过程中，如果找到相关的错误SQL示例，会在Response Guidelines之前添加负面示例
- 负面示例采用与现有提示词一致的格式结构，位于Response Guidelines之前：
  ```
  ===Tables
  [DDL信息]

  ===Additional Context
  [文档信息]

  ===Negative Examples
  下面是错误的SQL示例，请分析这些错误SQL的问题所在，并在生成新SQL时避免类似错误：

  问题: [用户问题]
  错误的SQL: [错误SQL]

  问题: [用户问题]
  错误的SQL: [错误SQL]

  ===Response Guidelines
  [响应指南和中文别名要求]
  ```

### 4. 智能过滤
- 只有当 `ENABLE_ERROR_SQL_PROMPT = True` 且找到相关错误SQL示例时，才会添加负面提示词
- 如果未找到相关错误SQL示例（返回空列表），不会添加任何负面提示词
- 支持相似度阈值过滤，只使用高质量的相关错误示例

## 使用方式

### 1. 训练错误SQL示例
```python
# 通过API接口添加错误SQL示例
POST /api/v0/training_error_question_sql
{
    "question": "查询所有用户信息",
    "sql": "SELECT * FROM users WHERE id = 'all'"  // 错误的SQL
}
```

### 2. 自动应用
- 配置启用后，系统会在每次SQL生成时自动查找并应用相关的错误SQL示例
- 无需额外操作，透明集成到现有的SQL生成流程中

## 技术优势
1. **智能相关性匹配**：基于向量相似度找到与当前问题最相关的错误示例
2. **质量控制**：通过相似度阈值确保只使用高质量的相关错误示例
3. **性能优化**：只在找到相关错误示例时才添加负面提示词，避免不必要的token消耗
4. **灵活配置**：支持通过配置参数灵活控制功能开关和阈值设置

