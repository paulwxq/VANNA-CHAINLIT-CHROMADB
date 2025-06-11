# Vanna-Chainlit-Chromadb 项目

## 项目结构

该项目主要组织结构如下：

- **core/**: 核心组件目录
  - **embedding_function.py**: 嵌入函数实现
  - **vanna_llm_factory.py**: Vanna实例工厂
- **common/**: 通用工具和辅助函数
- **customembedding/**: 自定义嵌入模型实现
- **customllm/**: 自定义语言模型实现
- **custompgvector/**: PgVector数据库集成
- **docs/**: 项目文档
- **public/**: 公共资源文件
- **training/**: 训练工具和数据
- **app_config.py**: 应用配置
- **chainlit_app.py**: Chainlit应用入口
- **flask_app.py**: Flask应用入口

## 训练数据与Function的对应关系

| 文件格式/扩展名 | 对应处理函数 | 用途说明 |
|----------------|-------------|----------|
| .ddl | train_ddl_statements() | 训练数据库定义语言文件 |
| .md / .markdown | train_documentation_blocks() | 训练Markdown格式的文档 |
| _pair.json / _pairs.json | train_json_question_sql_pairs() | 训练JSON格式的问答对 |
| _pair.sql / _pairs.sql | train_formatted_question_sql_pairs() | 训练格式化的问答对文件 |
| .sql (其他) | train_sql_examples() | 训练一般SQL示例文件 |


各种组合的行为总结
enable_thinking	stream (输入)	stream (实际)	行为描述
False	False	False	非流式模式，无thinking
False	True	True	流式模式，无thinking
True	False	True (强制)	流式模式，有thinking + 警告日志
True	True	True	流式模式，有thinking
当前的代码实现完全符合您的两个要求，逻辑正确且健壮！