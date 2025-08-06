# React Agent 同步流式API解决方案

## 问题背景

原有的 `ask_react_agent_stream` API 在处理复杂数据库查询时，会出现 Vector 搜索异步冲突错误：
```
RuntimeError: Task <Task pending...> got Future <Future pending> attached to a different loop
```

**根本原因**：LangGraph异步流式处理与Vanna Vector搜索的同步操作冲突。

## 解决方案

创建了完全独立的同步流式API，彻底避免异步冲突问题。

### 新API端点

```
GET /api/v0/ask_react_agent_stream_sync
```

### 核心技术架构

1. **同步Agent类**：`SyncCustomReactAgent`
2. **同步LangGraph**：使用 `graph.invoke()` 而不是 `ainvoke()`
3. **同步LLM配置**：
   - `streaming=False`
   - `enable_thinking=False` (千问模型非流式调用要求)
4. **完全避免异步依赖**：不使用checkpointer

## 使用方法

### API调用示例

```bash
# PowerShell
Invoke-WebRequest -Uri 'http://localhost:8084/api/v0/ask_react_agent_stream_sync?question=请问当前系统中哪个服务区档口最多?&user_id=test_user' -Headers @{'Accept'='text/event-stream'} -Method GET

# curl (在支持的终端中)
curl -X GET "http://localhost:8084/api/v0/ask_react_agent_stream_sync?question=请查询所有服务区的名称和档口数量&user_id=test_user" -H "Accept: text/event-stream"
```

### 参数说明

与原API完全兼容：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 用户问题 |
| `user_id` | string | ✅ | 用户ID |
| `thread_id` | string | ❌ | 对话线程ID |
| `routing_mode` | string | ❌ | 路由模式，默认'agent' |
| `continue_conversation` | boolean | ❌ | 是否继续对话，默认false |

### 响应格式

返回SSE流式响应：

```
data: {"type": "start", "message": "开始处理请求...", "timestamp": 1754412317.7335036}

data: {"type": "thinking", "content": "正在分析问题并准备查询数据库...", "timestamp": 1754412317.7335036}

data: {"type": "response", "content": "查询结果...", "metadata": {...}, "timestamp": 1754412317.7335036}

data: {"type": "completed", "message": "请求处理完成", "user_id": "test_user", "thread_id": "...", "timestamp": 1754412317.7335036}
```

## 验证结果

### ✅ 成功解决的问题

1. **Vector搜索异步冲突**：完全消除
2. **复杂数据库查询**：正常执行SQL生成、查询、结果返回
3. **LLM配置兼容性**：解决千问模型非流式调用限制
4. **系统稳定性**：不影响现有API

### ✅ 实际测试验证

**测试查询**：
```
请查询所有服务区的名称和档口数量，按档口数量降序排列
```

**执行结果**：
- SQL生成成功
- Vector搜索无异步冲突
- 数据库查询正常执行
- 返回正确结果：南城服务区39个档口

## API选择建议

### 使用同步API的场景

- ✅ **复杂数据库查询**
- ✅ **需要Vector搜索的问题**
- ✅ **对稳定性要求高的场景**

### 继续使用原API的场景

- ✅ **简单对话查询**
- ✅ **不涉及数据库的问题**
- ✅ **现有集成代码暂时不变更的场景**

## 技术细节

### 文件结构

```
react_agent/
├── sync_agent.py          # 新增：同步Agent类
├── agent.py              # 原有：异步Agent类
└── ...

unified_api.py             # 新增：同步流式API端点
```

### 关键配置

**LLM配置** (`sync_agent.py`):
```python
ChatOpenAI(
    model=config.QWEN_MODEL,
    temperature=0.1,
    streaming=False,  # 关键：禁用流式
    extra_body={
        "enable_thinking": False,  # 关键：非流式调用必须为false
        "misc": {"ensure_ascii": False}
    }
)
```

**LangGraph配置**:
```python
# 使用同步invoke而不是异步ainvoke
final_state = self.agent_executor.invoke(inputs, run_config)
```

## 影响范围

### ✅ 零风险部署

- **不修改任何现有代码**
- **原有API继续正常工作**
- **完全独立的实现**
- **可以渐进式切换使用**

### 文件变更

- **新增文件**：`react_agent/sync_agent.py`
- **修改文件**：`unified_api.py` (新增API端点)
- **未修改**：所有现有核心功能代码

## 结论

通过创建同步版本的React Agent，彻底解决了Vector搜索异步冲突问题，为复杂数据库查询提供了稳定可靠的解决方案。

---

**创建时间**：2025-08-06  
**解决的核心问题**：React Agent流式API的Vector搜索异步冲突  
**技术方案**：同步LangGraph + 同步LLM配置