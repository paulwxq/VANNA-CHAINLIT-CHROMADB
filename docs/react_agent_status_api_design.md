# React Agent状态监控API设计文档

## 1. 需求背景

在React Agent执行过程中，用户需要实时了解当前的执行状态，类似ChatGPT的"AI正在思考"效果。

**核心需求**：
- 提供状态查询API：`GET /api/v0/react/status/{thread_id}`
- 对应现有聊天接口：`POST /api/v0/ask_react_agent`
- 支持并发访问，不阻塞主要业务流程
- 显示具体的执行步骤和工具调用状态

## 2. 问题分析

### 2.1 并发阻塞问题

**问题现象**：
- 执行`/api/v0/ask_react_agent`时，无法同时调用`/api/v0/react/status/{thread_id}`
- 状态API必须等待聊天API完成后才能执行

**根因分析**：
```python
# 全局单例Agent实例
_react_agent_instance: Optional[Any] = None

# ask_react_agent API调用
agent_result = await _react_agent_instance.chat(...)
→ agent_executor.ainvoke() # 长时间执行，锁定Agent实例

# status API同时调用  
checkpoint_tuple = await _react_agent_instance.checkpointer.aget_tuple(read_config)
→ 访问同一个checkpointer实例 → 被阻塞
```

**核心原因**：
- 全局Agent实例的资源竞争
- StateGraph执行期间持续使用checkpointer
- AsyncRedisSaver可能存在内部锁定机制

### 2.2 AsyncRedisSaver并发性调研

通过LangGraph官方文档调研发现：

**支持并发的证据**：
```python
# 官方文档显示不同thread_id可以并发
config1 = {"configurable": {"thread_id": "1"}}
config2 = {"configurable": {"thread_id": "2"}}
# 理论上可以并发运行

# 异步API设计
async with AsyncRedisSaver.from_conn_string("redis://localhost:6379") as checkpointer:
    await checkpointer.aput(write_config, checkpoint, {}, {})
    loaded_checkpoint = await checkpointer.aget(read_config)
```

**结论**：AsyncRedisSaver本身支持并发，问题在于Agent实例的资源竞争。

### 2.3 状态判断问题

**`suggested_next_step`字段不可靠**：
- 测试发现：即使LangGraph执行完成，该字段仍显示执行中
- 原因：该字段表示"下一步要执行的节点"，不是"当前执行状态"

## 3. 解决方案设计

### 3.1 方案对比

| 方案 | 优点 | 缺点 | 可行性 |
|------|------|------|---------|
| 通过Agent API | 复用现有逻辑 | 资源竞争，并发阻塞 | ❌ |
| 直接Redis访问 | 完全独立，无阻塞 | 需要解析原始数据 | ✅ |
| 独立checkpointer | 避免竞争 | 复杂度高 | 🔶 |

**最终选择**：直接Redis访问方案

### 3.2 技术方案

**核心思路**：
1. 使用独立的Redis连接，绕过Agent实例
2. 直接读取Redis中的checkpoint原始数据
3. 通过分析messages列表判断真实执行状态
4. 根据工具调用情况提供详细状态信息

## 4. 实现设计

### 4.1 Redis数据结构分析

**Redis Key格式**：
```
checkpoint:wang1:20250729235038043:__empty__:1f06c944-6250-64c7-8021-00e2694c5546
```

**Redis Value结构**：
```json
{
  "checkpoint": {
    "channel_values": {
      "messages": [
        {
          "kwargs": {
            "type": "human|ai|tool",
            "content": "...",
            "tool_calls": [...],
            "name": "generate_sql|valid_sql|run_sql"
          }
        }
      ],
      "suggested_next_step": "..." // 不可靠，不使用
    }
  }
}
```

### 4.2 状态判断逻辑

**通过messages分析执行状态**：

1. **已完成**：最后一条AIMessage有完整内容且无tool_calls
2. **执行中**：
   - 最后一条AIMessage有tool_calls → 显示具体工具调用
   - 最后一条ToolMessage → 显示工具执行状态
   - 最后一条HumanMessage → AI思考中

### 4.3 工具状态映射

```python
TOOL_STATUS_MAPPING = {
    "generate_sql": {"name": "生成SQL中", "icon": "🔍"},
    "valid_sql": {"name": "验证SQL中", "icon": "✅"}, 
    "run_sql": {"name": "执行查询中", "icon": "⚡"},
}
```

## 5. 完整实现代码

### 5.1 API接口实现

```python
@app.route('/api/v0/react/status/<thread_id>', methods=['GET'])
async def get_react_agent_status_direct(thread_id: str):
    """直接访问Redis获取React Agent执行状态，绕过Agent实例资源竞争"""
    
    try:
        # 工具状态映射
        TOOL_STATUS_MAPPING = {
            "generate_sql": {"name": "生成SQL中", "icon": "🔍"},
            "valid_sql": {"name": "验证SQL中", "icon": "✅"}, 
            "run_sql": {"name": "执行查询中", "icon": "⚡"},
        }
        
        # 创建独立的Redis连接，不使用Agent的连接
        redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
        
        try:
            # 1. 查找该thread_id的所有checkpoint键
            pattern = f"checkpoint:{thread_id}:*"
            keys = await redis_client.keys(pattern)
            
            if not keys:
                from common.result import failed
                return jsonify(failed(message="未找到执行线程", code=404)), 404
            
            # 2. 获取最新的checkpoint键
            latest_key = sorted(keys)[-1]
            
            # 3. 直接从Redis获取原始JSON数据
            raw_checkpoint_data = await redis_client.get(latest_key)
            
            if not raw_checkpoint_data:
                from common.result import failed
                return jsonify(failed(message="无法读取checkpoint数据", code=500)), 500
            
            # 4. 解析JSON
            checkpoint = json.loads(raw_checkpoint_data)
            
            # 5. 提取messages
            messages = checkpoint.get("checkpoint", {}).get("channel_values", {}).get("messages", [])
            
            if not messages:
                status_data = {
                    "status": "running",
                    "name": "初始化中",
                    "icon": "🚀",
                    "timestamp": datetime.now().isoformat()
                }
                from common.result import success
                return jsonify(success(data=status_data, message="获取状态成功")), 200
            
            # 6. 分析最后一条消息
            last_message = messages[-1]
            last_msg_type = last_message.get("kwargs", {}).get("type", "")
            
            # 7. 判断执行状态
            if (last_msg_type == "ai" and 
                not last_message.get("kwargs", {}).get("tool_calls", []) and
                last_message.get("kwargs", {}).get("content", "").strip()):
                
                # 完成状态：AIMessage有完整回答且无tool_calls
                status_data = {
                    "status": "completed",
                    "name": "完成",
                    "icon": "✅",
                    "timestamp": datetime.now().isoformat()
                }
                
            elif (last_msg_type == "ai" and 
                  last_message.get("kwargs", {}).get("tool_calls", [])):
                
                # AI正在调用工具
                tool_calls = last_message.get("kwargs", {}).get("tool_calls", [])
                tool_name = tool_calls[0].get("name", "") if tool_calls else ""
                
                tool_info = TOOL_STATUS_MAPPING.get(tool_name, {
                    "name": f"调用{tool_name}中" if tool_name else "调用工具中",
                    "icon": "🔧"
                })
                
                status_data = {
                    "status": "running",
                    "name": tool_info["name"],
                    "icon": tool_info["icon"],
                    "timestamp": datetime.now().isoformat()
                }
                
            elif last_msg_type == "tool":
                # 工具执行完成，等待AI处理
                tool_name = last_message.get("kwargs", {}).get("name", "")
                tool_status = last_message.get("kwargs", {}).get("status", "")
                
                if tool_status == "success":
                    tool_info = TOOL_STATUS_MAPPING.get(tool_name, {"name": "处理中", "icon": "🔄"})
                    status_data = {
                        "status": "running", 
                        "name": f"{tool_info['name'].replace('中', '')}完成，AI处理中",
                        "icon": "🤖",
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    tool_info = TOOL_STATUS_MAPPING.get(tool_name, {
                        "name": f"执行{tool_name}中",
                        "icon": "⚙️"
                    })
                    status_data = {
                        "status": "running",
                        "name": tool_info["name"], 
                        "icon": tool_info["icon"],
                        "timestamp": datetime.now().isoformat()
                    }
                    
            elif last_msg_type == "human":
                # 用户刚提问，AI开始思考
                status_data = {
                    "status": "running",
                    "name": "AI思考中",
                    "icon": "🤖",
                    "timestamp": datetime.now().isoformat()
                }
                
            else:
                # 默认执行中状态
                status_data = {
                    "status": "running",
                    "name": "执行中",
                    "icon": "⚙️", 
                    "timestamp": datetime.now().isoformat()
                }
            
            from common.result import success
            return jsonify(success(data=status_data, message="获取状态成功")), 200
            
        finally:
            await redis_client.close()
            
    except Exception as e:
        logger.error(f"获取React Agent状态失败: {e}")
        from common.result import failed
        return jsonify(failed(message=f"获取状态失败: {str(e)}", code=500)), 500
```

### 5.2 响应格式示例

**执行中示例**：
```json
{
  "code": 200,
  "success": true,
  "message": "获取状态成功",
  "data": {
    "status": "running",
    "name": "生成SQL中",
    "icon": "🔍",
    "timestamp": "2025-01-31T12:34:56.789Z"
  }
}
```

**完成示例**：
```json
{
  "code": 200,
  "success": true,
  "message": "获取状态成功",
  "data": {
    "status": "completed",
    "name": "完成",
    "icon": "✅",
    "timestamp": "2025-01-31T12:35:20.123Z"
  }
}
```

## 6. 状态流转示例

基于实际的LangGraph执行流程：

1. **用户提问** → `{"status": "running", "name": "AI思考中", "icon": "🤖"}`

2. **AI调用generate_sql** → `{"status": "running", "name": "生成SQL中", "icon": "🔍"}`

3. **generate_sql完成** → `{"status": "running", "name": "生成SQL完成，AI处理中", "icon": "🤖"}`

4. **AI调用valid_sql** → `{"status": "running", "name": "验证SQL中", "icon": "✅"}`

5. **AI调用run_sql** → `{"status": "running", "name": "执行查询中", "icon": "⚡"}`

6. **AI生成最终回答** → `{"status": "completed", "name": "完成", "icon": "✅"}`

## 7. 使用方式

### 7.1 客户端轮询

```bash
# 开始对话
curl -X POST http://localhost:8084/api/v0/ask_react_agent \
  -H "Content-Type: application/json" \
  -d '{"question": "查询服务区信息", "user_id": "test"}'

# 轮询状态 (使用返回的thread_id)
curl http://localhost:8084/api/v0/react/status/test:20250131123456789
```

### 7.2 JavaScript轮询示例

```javascript
async function pollStatus(threadId) {
    const pollInterval = 1000; // 1秒轮询
    
    while (true) {
        try {
            const response = await fetch(`/api/v0/react/status/${threadId}`);
            const result = await response.json();
            
            if (result.success) {
                console.log(`${result.data.icon} ${result.data.name}`);
                
                if (result.data.status === 'completed') {
                    console.log('✅ 执行完成');
                    break;
                }
            }
            
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        } catch (error) {
            console.error('状态查询失败:', error);
            break;
        }
    }
}
```

## 8. 技术优势

1. **完全并发**：独立Redis连接，无资源竞争
2. **状态准确**：基于messages分析，比suggested_next_step可靠
3. **信息丰富**：显示具体工具调用状态，用户体验更好
4. **性能优秀**：直接Redis访问，跳过LangGraph封装层
5. **架构清晰**：不影响现有Agent实现，纯新增功能

## 9. 注意事项

1. **Redis连接管理**：每次请求创建独立连接，避免连接池竞争
2. **错误处理**：完善的异常处理，避免Redis连接泄露
3. **工具映射扩展**：新增工具时需更新TOOL_STATUS_MAPPING
4. **轮询频率**：建议1秒轮询，避免过度查询Redis

## 10. 后续优化

1. **缓存机制**：适当缓存状态，减少Redis查询频率
2. **WebSocket推送**：实现服务端主动推送状态变更
3. **状态历史**：记录状态变更历史，便于调试分析
4. **监控告警**：添加状态API的性能监控和异常告警

## 并发问题解决方案

### 问题根源
经测试确认，**WsgiToAsgi转换器是并发阻塞的根本原因**：
- WsgiToAsgi虽然能让WSGI应用在ASGI服务器运行，但不是真正的原生异步
- 内部可能使用线程池或其他机制导致请求串行化
- 即使使用独立Redis连接，仍然无法解决框架层面的并发限制

### 解决方案
使用**原生Flask多线程模式**：
```python
USE_WSGI_TO_ASGI = False  # 禁用WsgiToAsgi
app.run(host="0.0.0.0", port=8084, debug=False, threaded=True)
```

### 验证结果
- ✅ 状态API可以在ask_react_agent执行过程中立即响应
- ✅ 实现真正的并发访问，不再阻塞
- ✅ 完美支持实时状态监控功能

---

**文档版本**: v1.1 (新增并发解决方案)  
**创建时间**: 2025-01-31  
**适用范围**: unified_api.py React Agent状态监控功能 