# 数据库表API使用指南

本文档介绍数据库表查询相关的API接口，包括获取表列表和表结构分析功能。

## API概览

| API端点 | 功能 | 必需参数 | 可选参数 |
|---------|------|----------|----------|
| `POST /api/v0/database/tables` | 获取数据库表列表 | 无 | `db_connection`, `schema` |
| `POST /api/v0/database/table/ddl` | 获取表DDL和结构分析 | `table` | `db_connection`, `business_context`, `type` |

## 1. 获取数据库表列表

### 接口信息
- **URL**: `POST /api/v0/database/tables`
- **功能**: 获取指定数据库中的表列表
- **特点**: 纯数据库查询，不涉及AI功能

### 请求参数

| 参数名 | 类型 | 必需 | 说明 | 示例 |
|--------|------|------|------|------|
| `db_connection` | string | 否 | PostgreSQL连接字符串<br/>不传则使用默认配置 | `"postgresql://user:pass@host:port/db"` |
| `schema` | string | 否 | Schema名称，支持逗号分隔多个<br/>默认为"public" | `"public,ods,dw"` |

### 请求示例

#### 使用默认数据库配置
```json
{
    "schema": "public,ods"
}
```

#### 使用指定数据库
```json
{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/bank_db",
    "schema": "public"
}
```

#### 最简调用（使用所有默认值）

此时的数据库连接配置来自于app_config.py

```json
{}
```

### 响应示例

```json
{
    "code": 200,
    "data": {
        "db_connection_info": {
            "database": "highway_db"
        },
        "response": "获取表列表成功",
        "schemas": [
            "public"
        ],
        "tables": [
            "public.bss_branch_copy",
            "public.bss_business_day_data",
            "public.bss_car_day_count",
            "public.bss_company",
            "public.bss_section_route",
            "public.bss_section_route_area_link",
            "public.bss_service_area",
            "public.bss_service_area_mapper"
        ],
        "total": 8
    },
    "message": "操作成功",
    "success": true
}
```

## 2. 获取表DDL和结构分析

### 接口信息
- **URL**: `POST /api/v0/database/table/ddl`
- **功能**: 获取表的DDL语句或Markdown文档，支持AI智能注释生成
- **特点**: 结合数据库查询和AI分析能力

### 请求参数

| 参数名 | 类型 | 必需 | 说明 | 示例 |
|--------|------|------|------|------|
| `table` | string | **是** | 表名，支持schema.table格式 | `"public.bank_churners"` |
| `db_connection` | string | 否 | PostgreSQL连接字符串<br/>不传则使用默认配置 | `"postgresql://user:pass@host:port/db"` |
| `business_context` | string | 否 | 业务上下文描述<br/>传入则启用AI注释生成 | `"银行信用卡持卡人信息"` |
| `type` | string | 否 | 输出类型：`ddl`/`md`/`both`<br/>默认为"ddl" | `"md"` |

### 请求示例

#### 基础DDL获取（使用默认配置）
```json
{
    "table": "public.bank_churners"
}
```

```json
{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/bank_db",
    "table": "public.bank_churners",
    "business_context": "银行信用卡用户统计表"
}
```

注意：只有提供 "business_context" 参数且不为空时，才会在返回结果中生成字段注释。

```json
{
    "code": 200,
    "data": {
        "ddl": "-- 中文名: 银行信用卡客户流失分析表\n-- 描述: 银行信用卡客户流失分析表，记录用户人口统计特征及流失状态，用于预测客户流失风险并制定客户保留策略。\ncreate table public.bank_churners (\n  client_num bigint not null  -- 客户编号，主键,\n  attrition_flag varchar(32)  -- 客户流失标识,\n  customer_age smallint       -- 客户年龄,\n  gender varchar(8)           -- 性别,\n  dependent_count smallint    -- 家属数量,\n  education_level varchar(32) -- 学历等级,\n  marital_status varchar(16)  -- 婚姻状况,\n  income_category varchar(32) -- 收入等级,\n  card_category varchar(16)   -- 信用卡类别,\n  months_on_book smallint     -- 开户月份数,\n  credit_limit numeric(12,2)  -- 信用额度,\n  total_revolving_bal numeric(12,2) -- 总循环余额,\n  avg_open_to_buy numeric(12,2) -- 平均可用额度,\n  total_amt_chng_q4_q1 double precision -- 季度交易金额变化率,\n  total_trans_amt numeric(12,2) -- 总交易金额,\n  total_trans_ct smallint     -- 总交易次数,\n  total_ct_chng_q4_q1 double precision -- 季度交易次数变化率,\n  avg_utilization_ratio double precision -- 平均利用率,\n  nb_classifier_attrition_flag_1 double precision -- 流失预测模型1得分,\n  nb_classifier_attrition_flag_2 double precision -- 流失预测模型2得分,\n  primary key (client_num)\n);",
        "fields": [
            {
                "comment": "客户编号",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": true,
                "name": "client_num",
                "nullable": false,
                "type": "bigint"
            },
            {
                "comment": "客户流失标识",
                "default_value": null,
                "enum_values": [
                    "Existing Customer",
                    "Attrited Customer"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "attrition_flag",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "客户年龄",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "customer_age",
                "nullable": true,
                "type": "smallint"
            },
            {
                "comment": "性别",
                "default_value": null,
                "enum_values": [
                    "F",
                    "M"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "gender",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "家属数量",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "dependent_count",
                "nullable": true,
                "type": "smallint"
            },
            {
                "comment": "学历等级",
                "default_value": null,
                "enum_values": [
                    "Graduate",
                    "High School",
                    "Unknown",
                    "Uneducated",
                    "College",
                    "Post-Graduate",
                    "Doctorate"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "education_level",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "婚姻状况",
                "default_value": null,
                "enum_values": [
                    "Married",
                    "Single",
                    "Unknown",
                    "Divorced"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "marital_status",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "收入等级",
                "default_value": null,
                "enum_values": [
                    "Less than $40K",
                    "$40K - $60K",
                    "$80K - $120K",
                    "$60K - $80K",
                    "Unknown",
                    "$120K +"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "income_category",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "信用卡类别",
                "default_value": null,
                "enum_values": [
                    "Blue",
                    "Silver",
                    "Gold",
                    "Platinum"
                ],
                "is_enum": true,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "card_category",
                "nullable": true,
                "type": "character varying"
            },
            {
                "comment": "开户月份数",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "months_on_book",
                "nullable": true,
                "type": "smallint"
            },
            {
                "comment": "信用额度",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "credit_limit",
                "nullable": true,
                "type": "numeric"
            },
            {
                "comment": "总循环余额",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "total_revolving_bal",
                "nullable": true,
                "type": "numeric"
            },
            {
                "comment": "平均可用额度",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "avg_open_to_buy",
                "nullable": true,
                "type": "numeric"
            },
            {
                "comment": "季度交易金额变化率",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "total_amt_chng_q4_q1",
                "nullable": true,
                "type": "double precision"
            },
            {
                "comment": "总交易金额",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "total_trans_amt",
                "nullable": true,
                "type": "numeric"
            },
            {
                "comment": "总交易次数",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "total_trans_ct",
                "nullable": true,
                "type": "smallint"
            },
            {
                "comment": "季度交易次数变化率",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "total_ct_chng_q4_q1",
                "nullable": true,
                "type": "double precision"
            },
            {
                "comment": "平均利用率",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "avg_utilization_ratio",
                "nullable": true,
                "type": "double precision"
            },
            {
                "comment": "流失预测模型1得分",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "nb_classifier_attrition_flag_1",
                "nullable": true,
                "type": "double precision"
            },
            {
                "comment": "流失预测模型2得分",
                "default_value": null,
                "enum_values": null,
                "is_enum": false,
                "is_foreign_key": false,
                "is_primary_key": false,
                "name": "nb_classifier_attrition_flag_2",
                "nullable": true,
                "type": "double precision"
            }
        ],
        "generation_info": {
            "business_context": "银行信用卡用户统计表",
            "database": "bank_db",
            "has_llm_comments": true,
            "output_type": "ddl"
        },
        "response": "获取表DDL成功",
        "table_info": {
            "comment": "银行信用卡客户流失分析表，记录用户人口统计特征及流失状态，用于预测客户流失风险并制定客户保留策略。",
            "field_count": 20,
            "full_name": "public.bank_churners",
            "row_count": 10127,
            "schema_name": "public",
            "table_name": "bank_churners",
            "table_size": "2008 kB"
        }
    },
    "message": "操作成功",
    "success": true
}
```





#### 生成智能注释的Markdown文档

```json
{
    "table": "public.bank_churners",
    "business_context": "银行信用卡持卡人信息表，用于分析客户流失情况",
    "type": "md"
}
```

#### 指定数据库获取DDL和MD
```json
{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/bank_db",
    "table": "public.bank_churners",
    "business_context": "银行信用卡持卡人信息",
    "type": "both"
}
```

### 响应示例

#### DDL模式响应
```json
{
    "success": true,
    "code": 200,
    "message": "获取表DDL成功",
    "data": {
        "ddl": "-- 中文名: 银行信用卡持卡人信息表\ncreate table public.bank_churners (\n  client_num bigint not null,\n  attrition_flag varchar(32),\n  ...\n);",
        "table_info": {
            "table_name": "bank_churners",
            "schema_name": "public",
            "full_name": "public.bank_churners",
            "comment": "银行信用卡持卡人信息表，记录客户流失状态、人口统计特征及账户活跃度数据",
            "field_count": 20,
            "row_count": 10127,
            "table_size": "2008 kB"
        },
        "fields": [
            {
                "name": "client_num",
                "type": "bigint",
                "nullable": false,
                "comment": "客户编号",
                "is_primary_key": true,
                "is_foreign_key": false,
                "default_value": null,
                "is_enum": false,
                "enum_values": null
            },
            {
                "name": "attrition_flag",
                "type": "character varying",
                "nullable": true,
                "comment": "客户流失标志",
                "is_primary_key": false,
                "is_foreign_key": false,
                "default_value": null,
                "is_enum": true,
                "enum_values": ["Existing Customer", "Attrited Customer"]
            }
        ],
        "generation_info": {
            "business_context": "银行信用卡持卡人信息",
            "output_type": "ddl",
            "has_llm_comments": true,
            "database": "bank_db"
        }
    }
}
```

## 功能特性说明

### AI智能注释功能

当传入 `business_context` 参数时，系统会：

1. **生成中文注释**: 基于业务上下文为表和字段生成准确的中文注释
2. **识别枚举字段**: 自动检测可能的枚举类型字段（如状态、类型、级别等）
3. **验证枚举值**: 查询数据库获取字段的实际枚举值
4. **优化字段描述**: 结合字段名、数据类型和样例数据生成更准确的描述

### 输出类型说明

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `ddl` | 返回CREATE TABLE语句 | 数据库迁移、表结构复制 |
| `md` | 返回Markdown格式文档 | 文档生成、团队共享 |
| `both` | 同时返回DDL和MD | 完整的表分析需求 |

### 默认数据库配置

当不传入 `db_connection` 参数时，系统会自动使用 `app_config.py` 中的 `APP_DB_CONFIG` 配置：

- 便于内部系统调用
- 减少重复的连接参数传递
- 保持与其他服务的数据库一致性

## 错误处理

### 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 400 | 缺少必需参数 | 检查请求参数，确保传入必需的参数 |
| 500 | 数据库连接失败 | 检查数据库连接字符串和网络连接 |
| 500 | 表不存在 | 确认表名正确，检查schema和表是否存在 |

### 错误响应示例

```json
{
    "success": false,
    "code": 400,
    "message": "请求参数错误",
    "data": {
        "response": "缺少必需参数：table",
        "missing_params": ["table"],
        "timestamp": "2025-07-02T10:30:00"
    }
}
```

## 使用注意事项

### 性能考虑

1. **表列表查询**: 速度较快，适合频繁调用
2. **DDL分析**: 涉及AI处理，响应时间较长（5-30秒）
3. **大表处理**: 系统会自动进行智能采样，避免性能问题

### 安全考虑

1. **数据库连接**: 使用独立连接，不影响其他服务
2. **权限要求**: 需要数据库的SELECT权限
3. **并发安全**: 支持多用户同时调用，无资源冲突

### 最佳实践

1. **内部调用**: 推荐不传 `db_connection`，使用默认配置
2. **外部调用**: 明确传入 `db_connection` 参数
3. **文档生成**: 传入详细的 `business_context` 以获得更好的AI注释
4. **批量处理**: 先调用表列表API获取所有表，再逐个分析

## 示例代码

### Python调用示例

```python
import requests

# 获取表列表
def get_tables(schema="public"):
    url = "http://localhost:8084/api/v0/database/tables"
    data = {"schema": schema}
    response = requests.post(url, json=data)
    return response.json()

# 获取表DDL
def get_table_ddl(table, business_context=None, output_type="ddl"):
    url = "http://localhost:8084/api/v0/database/table/ddl"
    data = {
        "table": table,
        "type": output_type
    }
    if business_context:
        data["business_context"] = business_context
    
    response = requests.post(url, json=data)
    return response.json()

# 使用示例
tables = get_tables("public")
ddl = get_table_ddl("public.bank_churners", "银行客户信息", "md")
```

### JavaScript调用示例

```javascript
// 获取表列表
async function getTables(schema = 'public') {
    const response = await fetch('/api/v0/database/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema })
    });
    return await response.json();
}

// 获取表DDL
async function getTableDDL(table, businessContext = null, type = 'ddl') {
    const data = { table, type };
    if (businessContext) {
        data.business_context = businessContext;
    }
    
    const response = await fetch('/api/v0/database/table/ddl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return await response.json();
}
```

## 更新日志

- **v1.0** (2025-07-02): 初始版本，支持基础的表查询和DDL生成
- **v1.1** (2025-07-02): 新增AI智能注释功能，支持枚举字段识别
- **v1.2** (2025-07-02): `db_connection` 参数改为可选，支持使用默认配置

---

如有问题或建议，请联系开发团队。 