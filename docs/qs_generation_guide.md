# Question-SQL生成功能使用指南

## 功能概述

Question-SQL生成功能是Schema Tools的扩展模块，用于从已生成的DDL和MD文件自动生成高质量的Question-SQL训练数据对。

## 主要特性

1. **表清单去重**：自动去除重复的表名，并在日志中报告
2. **文件完整性验证**：验证DDL和MD文件数量，详细报告缺失文件
3. **智能主题提取**：使用LLM自动提取业务分析主题
4. **批量问题生成**：每个主题生成10个Question-SQL对
5. **元数据管理**：生成包含INSERT语句的metadata.txt文件
6. **中间结果保存**：支持中断恢复

## 使用步骤

### 步骤1：生成DDL和MD文件

```bash
python -m schema_tools \
  --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./output \
  --pipeline full \
  --verbose
```

### 步骤2：手动检查生成的文件

在output目录下检查：
- *.ddl文件（表结构定义）
- *_detail.md文件（表详细文档）

### 步骤3：生成Question-SQL对

```bash
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db \
  --verbose
```

## 输出文件说明

### 1. Question-SQL数据文件
- 文件名：`qs_<db_name>_<timestamp>_pair.json`
- 格式：
```json
[
  {
    "question": "业务问题描述？",
    "sql": "SELECT ... FROM ... WHERE ...;"
  }
]
```

### 2. 主题元数据文件
- 文件名：`metadata.txt`
- 内容：包含CREATE TABLE和INSERT语句
- 示例：
```sql
-- Schema Tools生成的主题元数据
-- 业务背景: 高速公路服务区管理系统
-- 生成时间: 2024-01-01 10:00:00
-- 数据库: highway_db

CREATE TABLE IF NOT EXISTS metadata (
    id SERIAL PRIMARY KEY,
    topic_name VARCHAR(100) NOT NULL,
    description TEXT,
    related_tables TEXT[],
    keywords TEXT[],
    focus_areas TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO metadata(topic_name, description, related_tables, keywords, focus_areas) VALUES
(
  '日营业数据分析',
  '基于 bss_business_day_data 表，分析每个服务区和档口每天的营业收入、订单数量、支付方式等',
  '{bss_business_day_data,bss_branch,bss_service_area}',
  '{收入,订单,支付方式,日报表}',
  '{收入趋势,服务区对比,支付方式分布}'
);
```

### 3. 中间结果文件（如有中断）
- 文件名：`qs_intermediate_<timestamp>.json`
- 用途：保存已完成的主题结果，支持断点恢复

## 配置参数

在`schema_tools/config.py`中的`qs_generation`部分：

```python
"qs_generation": {
    "max_tables": 20,              # 最大表数量限制
    "theme_count": 5,              # 生成主题数量
    "questions_per_theme": 10,     # 每主题问题数
    "max_concurrent_themes": 1,    # 并行处理主题数
    "continue_on_theme_error": True,  # 主题失败是否继续
    "save_intermediate": True,     # 是否保存中间结果
}
```

## 注意事项

1. **表数量限制**：默认最多处理20个表，超过需要分批处理
2. **表名去重**：表清单中的重复表会自动去除，日志会显示去重统计
3. **文件验证**：如果DDL/MD文件数量不匹配，会详细列出缺失的表
4. **LLM依赖**：需要配置好vanna实例的LLM
5. **错误恢复**：如果生成过程中断，中间结果会保存，下次可手动恢复

## 常见问题

### Q: 表清单中有重复表怎么办？
A: 系统会自动去重，并在日志中报告：
```
表清单去重统计: 原始11个表，去重后8个表，移除了3个重复项
```

### Q: 文件验证失败显示缺少某些表？
A: 检查日志中的详细信息：
```
缺失的DDL文件对应的表: bss_company, bss_service_area
缺失的MD文件对应的表: bss_company
```

### Q: 如何使用生成的metadata.txt？
A: 可以直接在PostgreSQL中执行：
```bash
psql -U postgres -d your_database -f output/metadata.txt
```

### Q: 生成中断了怎么办？
A: 查看output目录下的`qs_intermediate_*.json`文件，其中包含已完成的主题结果。 