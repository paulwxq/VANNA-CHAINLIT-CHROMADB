# valid_sql 测试说明

## 概述

简化版测试脚本，专门测试 `valid_sql` 工具的三种错误场景：

1. **表不存在** - `SELECT * FROM non_existent_table LIMIT 1`
2. **字段不存在** - `SELECT non_existent_field FROM bss_business_day_data LIMIT 1`  
3. **语法错误** - `SELECT * FROM bss_business_day_data WHERE`

## 使用方法

```bash
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 运行测试
python test_valid_sql_simple.py
```

## 测试内容

脚本会依次测试三种错误场景：

1. **直接测试 valid_sql 工具** - 验证工具是否正确识别错误
2. **测试 LLM 响应** - 观察 LLM 收到错误后如何处理

## 预期结果

- `valid_sql` 工具应该正确识别并报告错误
- LLM 应该理解错误原因并提供有意义的响应 