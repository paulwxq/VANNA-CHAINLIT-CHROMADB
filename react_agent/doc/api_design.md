# Custom React Agent API 概要设计

## 1. 项目概述

基于 `./test/custom_react_agent` 模块开发一个RESTful API，提供智能问答服务。用户通过POST请求提交问题，系统通过LangGraph Agent处理并返回格式化的JSON结果。

## 2. API设计

### 2.1 接口定义

**端点**: `POST /api/chat`

**请求格式**:
```json
{
    "question": "请问中国共有多少个充电桩",
    "user_id": "Paul",      // 可选，默认为"guest"
    "thread_id": "xxxx"     // 可选，不传则自动生成新会话
}
```

**响应格式**:
```json
{
    "code": 200,
    "message": "操作成功",
    "success": true,
    "data": {
        // 核心响应内容
        "response": "根据查询结果，当前数据库中共有3个服务区的收入数据...",
        "sql": "SELECT COUNT(*) FROM charging_stations;",  // 可选，仅当执行SQL时存在
        "records": {  // 可选，仅当有查询结果时存在
            "columns": ["服务区名称", "总收入"],
            "rows": [
                {"服务区名称": "庐山服务区", "总收入": "7024226.1500"},
                {"服务区名称": "三清山服务区", "总收入": "6929288.3300"}
            ],
            "total_row_count": 3,
            "is_limited": false
        },
        
        // Agent元数据
        "react_agent_meta": {
            "thread_id": "Paul:20250101120030001",
            "conversation_rounds": 5,
            "tools_used": ["generate_sql", "run_sql"],
            "execution_path": ["agent", "prepare_tool_input", "tools", "format_final_response"],
            "total_messages": 11,
            "sql_execution_count": 1,
            "context_injected": true,
            "agent_version": "custom_react_v1"
        },
        
        "timestamp": "2025-01-01T12:00:30.123456"
    }
}
```

**错误响应格式**:
```json
{
    "code": 500,
    "message": "SQL执行失败",
    "success": false,
    "error": "详细错误信息",
    "data": {
        "react_agent_meta": {
            "thread_id": "Paul:20250101120030001",
            "execution_path": ["agent", "prepare_tool_input", "tools", "error"],
            "agent_version": "custom_react_v1"
        },
        "timestamp": "2025-01-01T12:00:30.123456"
    }
}
```

### 2.2 状态码定义

| Code | 描述 | 场景 |
|------|------|------|
| 200  | 成功 | 正常处理完成 |
| 400  | 请求错误 | 参数缺失或格式错误 |
| 500  | 服务器错误 | Agent执行异常 |

## 3. 架构设计

### 3.1 分层处理架构

```
用户请求 → API层 → Agent处理 → format_final_response节点 → API层包装 → JSON响应
           ↓        ↓              ↓                      ↓
        参数验证   核心逻辑      生成data内容           包装HTTP格式
```

### 3.2 职责分工

#### **API层 (api.py)**
- 请求参数验证和预处理
- HTTP响应格式包装 (code, message, success)
- 错误处理和异常捕获
- 时间戳添加
- Thread ID管理

#### **format_final_response节点**
- 从Agent State提取核心数据
- 生成response、sql、records字段
- 收集和整理react_agent_meta元数据
- 输出标准化的data结构

#### **chat()函数**
- 保持简化格式，专注于对接shell.py
- 不参与API响应格式化
- 保留现有的测试功能

### 3.3 数据流转

```mermaid
graph TD
    A[用户POST请求] --> B[API层参数验证]
    B --> C[调用Agent.chat()]
    C --> D[Agent执行StateGraph]
    D --> E[format_final_response节点]
    E --> F[生成结构化data]
    F --> G[返回到API层]
    G --> H[包装HTTP响应格式]
    H --> I[返回JSON响应]
```

## 4. Thread ID管理策略

### 4.1 生成规则
- **格式**: `{user_id}:{timestamp_with_milliseconds}`
- **示例**: `Paul:20250101120030001`
- **默认用户**: 未传递user_id时使用`guest`

### 4.2 会话管理
```python
# 新会话：不传thread_id
{"question": "你好", "user_id": "Paul"}

# 继续会话：传递thread_id
{"question": "详细解释", "user_id": "Paul", "thread_id": "Paul:20250101120030001"}

# 重新开始：不传thread_id
{"question": "新问题", "user_id": "Paul"}
```

### 4.3 前端集成建议
```javascript
class ChatSession {
    constructor(userId = 'guest') {
        this.userId = userId;
        this.threadId = null;
    }
    
    // 发送消息
    async sendMessage(question) {
        const payload = {
            question,
            user_id: this.userId
        };
        
        // 继续会话
        if (this.threadId) {
            payload.thread_id = this.threadId;
        }
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        // 保存thread_id用于后续对话
        if (result.success) {
            this.threadId = result.data.react_agent_meta.thread_id;
        }
        
        return result;
    }
    
    // 开始新会话
    startNewSession() {
        this.threadId = null;
    }
}
```

## 5. 实现计划

### 5.1 新增文件

#### **api.py**
```python
"""
Custom React Agent API 服务
提供RESTful接口用于智能问答
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime

def validate_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证请求数据"""
    errors = []
    
    question = data.get('question', '')
    if not question or not question.strip():
        errors.append('问题不能为空')
    elif len(question) > 2000:
        errors.append('问题长度不能超过2000字符')
    
    if errors:
        raise ValueError('; '.join(errors))
    
    return {
        'question': question.strip(),
        'user_id': data.get('user_id', 'guest'),
        'thread_id': data.get('thread_id')
    }

app = Flask(__name__)
CORS(app)

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """智能问答接口"""
    data = request.get_json()
    validated_data = validate_request_data(data)
    # 实现逻辑...
    return jsonify({"code": 200, "success": True, "data": result})
```

### 5.2 修改现有文件

#### **agent.py**
- 修改`_format_final_response_node`方法
- 增强数据提取和元数据收集逻辑
- 保持`chat()`函数的简化格式

#### **state.py** 
- 如果需要，可添加额外的状态字段用于元数据收集

### 5.3 开发步骤

1. **第一阶段：核心功能**
   - 实现API基础框架
   - 修改format_final_response节点
   - 实现基本的请求/响应处理

2. **第二阶段：增强功能**
   - 完善元数据收集
   - 实现错误处理机制
   - 添加参数验证

3. **第三阶段：测试优化**
   - API测试和调试
   - 性能优化
   - 文档完善

## 6. 数据格式详细说明

### 6.1 核心字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| response | string | 是 | LLM的回答或SQL结果总结 |
| sql | string | 否 | 执行的SQL语句，仅在数据库查询时存在 |
| records | object | 否 | 查询结果数据，仅在有结果时存在 |

### 6.2 records字段结构
```json
{
    "columns": ["列名1", "列名2"],           // 列名数组
    "rows": [                              // 数据行数组
        {"列名1": "值1", "列名2": "值2"}
    ],
    "total_row_count": 100,                // 总行数
    "is_limited": false                    // 是否被截断
}
```

### 6.3 react_agent_meta字段
```json
{
    "thread_id": "用户会话ID",
    "conversation_rounds": 5,              // 当前对话轮次
    "tools_used": ["工具名称"],           // 本次使用的工具
    "execution_path": ["节点路径"],       // 执行路径
    "total_messages": 11,                 // 消息总数
    "sql_execution_count": 1,             // SQL执行次数
    "context_injected": true,             // 是否注入上下文
    "agent_version": "custom_react_v1"    // Agent版本
}
```

## 7. 兼容性考虑

### 7.1 shell.py适配
- 保持`chat()`函数的简化返回格式
- shell.py继续使用原有的交互逻辑
- 新的API格式不影响命令行测试

### 7.2 现有功能保留
- 保持所有现有的Agent功能
- Redis持久化功能继续工作
- 工具调用机制不变

## 8. 扩展性设计

### 8.1 版本控制
- API版本通过URL路径区分: `/api/v1/chat`
- Agent版本通过react_agent_meta.agent_version标识

### 8.2 配置化
- 支持通过配置文件调整返回字段
- 支持自定义元数据收集策略

### 8.3 监控和日志
- 请求/响应日志记录
- 性能指标收集
- 错误统计和告警

## 9. 安全考虑

### 9.1 输入验证
- 问题长度限制
- user_id格式验证
- SQL注入防护

### 9.2 资源保护
- 请求频率限制
- 超时控制
- 内存使用监控

---

**文档版本**: v1.0  
**创建时间**: 2025-01-01  
**作者**: AI Assistant  
**适用范围**: test/custom_react_agent 模块 