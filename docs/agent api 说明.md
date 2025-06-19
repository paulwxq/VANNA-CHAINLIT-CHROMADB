# Agent API 使用说明

## API使用示例

### 1. 数据库查询示例

**请求：**
```http
POST /api/v0/ask_agent
Content-Type: application/json

{
    "question": "查询本月销售额前10的客户",
    "session_id": "user_123_session"
}
```

**响应：**
```json
{
    "success": true,
    "code": 200,
    "message": "success",
    "data": {
        "response": "本月销售额前10的客户查询结果如下...",
        "type": "DATABASE",
        "sql": "SELECT customer_name, SUM(amount) as total_sales FROM sales WHERE month = '2024-01' GROUP BY customer_name ORDER BY total_sales DESC LIMIT 10",
        "data_result": {
            "rows": [...],
            "columns": ["customer_name", "total_sales"],
            "row_count": 10
        },
        "summary": "查询结果显示...",
        "execution_path": ["classify", "agent_database", "format_response"],
        "classification_info": {
            "confidence": 0.95,
            "reason": "匹配数据库关键词: ['数据类:销量']",
            "method": "rule_based"
        }
    }
}
```

### 2. 聊天对话示例

**请求：**
```http
POST /api/v0/ask_agent
Content-Type: application/json

{
    "question": "你好，请介绍一下这个平台的功能",
    "session_id": "user_456_session"
}
```

**响应：**
```json
{
    "success": true,
    "code": 200,
    "message": "success",
    "data": {
        "response": "您好！我是Citu智能数据问答平台的AI助手...",
        "type": "CHAT",
        "execution_path": ["classify", "agent_chat", "format_response"],
        "classification_info": {
            "confidence": 0.8,
            "reason": "匹配聊天关键词: ['你好']",
            "method": "rule_based"
        }
    }
}
```

### 3. 健康检查示例

**请求：**
```http
GET /api/v0/agent_health
```

**响应：**
```json
{
    "success": true,
    "code": 200,
    "message": "success",
    "data": {
        "status": "healthy",
        "test_result": true,
        "workflow_compiled": true,
        "tools_count": 4,
        "message": "Agent健康检查完成",
        "checks": {
            "agent_creation": true,
            "tools_import": true,
            "llm_connection": true,
            "classifier_ready": true
        }
    }
}
```

### 文件对应关系
```
vannva-langgraph/
├── agent/                    # 新增目录
│   ├── __init__.py          # 新增
│   ├── state.py             # 新增
│   ├── classifier.py        # 新增
│   ├── utils.py             # 新增
│   ├── citu_agent.py        # 新增
│   └── tools/               # 新增子目录
│       ├── __init__.py      # 新增
│       ├── sql_generation.py    # 新增
│       ├── sql_execution.py     # 新增
│       ├── summary_generation.py # 新增
│       └── general_chat.py      # 新增
├── citu_app.py              # 修改（添加2个API）
├── requirements.txt         # 更新（添加依赖）
└── 其他现有文件...          # 保持不变
```