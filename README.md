
更新后的训练数据与Function的对应关系
| 文件格式/扩展名 | 对应处理函数 | 用途说明 |
|----------------|-------------|----------|
| .ddl | train_ddl_statements() | 训练数据库定义语言文件 |
| .md / .markdown | train_documentation_blocks() | 训练Markdown格式的文档 |
| _pair.json / _pairs.json | train_json_question_sql_pairs() | 训练JSON格式的问答对 |
| _pair.sql / _pairs.sql | train_formatted_question_sql_pairs() | 训练格式化的问答对文件 |
| .sql (其他) | train_sql_examples() | 训练一般SQL示例文件 |