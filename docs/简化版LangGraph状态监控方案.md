## 简化版LangGraph状态监控方案

### 🎯 **核心理念**
像ChatGPT一样，只告诉用户"AI正在思考"，不显示百分比进度，专注于当前执行状态。

### 📡 **单一API设计**

**接口**: `GET /api/status/{thread_id}`

**响应格式**:
```json
{
  "status": "running|completed",
  "name": "AI思考中",
  "icon": "🤖",
  "timestamp": "2025-07-30T15:30:45.123Z"
}
```

### 🔄 **状态映射**
基于您的LangGraph流程图节点：

| 节点 | 显示名称 | 图标 |
|------|----------|------|
| `__start__` | 开始 | 🚀 |
| `agent` | AI思考中 | 🤖 |
| `prepare_tool_input` | 准备工具 | 🔧 |
| `tools` | 执行查询 | ⚙️ |
| `update_state_after_tool` | 处理结果 | 🔄 |
| `format_final_response` | 生成回答 | 📝 |
| `__end__` | 完成 | ✅ |

### 🏗️ **实现逻辑**
1. 从Redis获取最新checkpoint
2. 读取`suggested_next_step`字段
3. 如果为空或`__end__` → 返回completed
4. 否则 → 返回running + 对应状态名称

### 💡 **使用方式**

**客户端轮询**:
```bash
# Postman测试
GET http://localhost:5000/api/status/wang1:20250729235038043

# 返回示例1 (执行中)
{
  "status": "running",
  "name": "AI思考中", 
  "icon": "🤖",
  "timestamp": "2025-07-30T15:30:45.123Z"
}

# 返回示例2 (完成)
{
  "status": "completed",
  "name": "完成",
  "icon": "✅", 
  "timestamp": "2025-07-30T15:31:20.456Z"
}
```

**客户端实现**:
```javascript
// 每秒轮询，直到status=completed就停止
setInterval(() => {
  fetch('/api/status/thread_id')
    .then(r => r.json())
    .then(data => {
      console.log(`${data.icon} ${data.name}`);
      if (data.status === 'completed') {
        // 停止轮询
      }
    });
}, 1000);
```

### ✨ **方案优势**
- **极简**: 只有4个字段，一个API
- **准确**: 基于真实的checkpoint状态
- **直观**: 像ChatGPT一样的用户体验
- **轻量**: 最小化网络传输和服务器负载
- **可靠**: 直接读取LangGraph的执行状态

这就是您要的最简化版本 - 一个API，几个字段，专注核心功能！



**简化LangGraph状态API** 的代码：        

```python

from flask import Flask, jsonify
import redis
import json
from datetime import datetime

app = Flask(__name__)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)


# 简单的节点状态映射

NODE_STATUS = {
    "__start__": {"name": "开始", "icon": "🚀"},
    "agent": {"name": "AI思考中", "icon": "🤖"},
    "prepare_tool_input": {"name": "准备工具", "icon": "🔧"},
    "tools": {"name": "执行查询", "icon": "⚙️"},
    "update_state_after_tool": {"name": "处理结果", "icon": "🔄"},
    "format_final_response": {"name": "生成回答", "icon": "📝"},
    "__end__": {"name": "完成", "icon": "✅"}
}

@app.route('/api/status/<thread_id>')
def get_status(thread_id):
    try:
        # 查找最新checkpoint
        pattern = f"checkpoint:{thread_id}:*"
        keys = redis_client.keys(pattern)
    
    if not keys:
        return jsonify({"error": "未找到执行线程"}), 404
    
    # 获取最新checkpoint
    latest_key = sorted(keys)[-1]
    checkpoint_data = redis_client.get(latest_key)
    
    if not checkpoint_data:
        return jsonify({"error": "无法读取数据"}), 500
    
    checkpoint = json.loads(checkpoint_data)
    suggested_next_step = checkpoint.get('suggested_next_step', '')
    
    # 判断状态
    if not suggested_next_step or suggested_next_step == "__end__":
        # 完成了
        return jsonify({
            "status": "completed",
            "name": "完成",
            "icon": "✅",
            "timestamp": datetime.now().isoformat()
        })
    else:
        # 正在执行
        node_info = NODE_STATUS.get(suggested_next_step, {
            "name": "执行中",
            "icon": "⚙️"
        })
        
        return jsonify({
            "status": "running",
            "name": node_info["name"],
            "icon": node_info["icon"],
            "timestamp": datetime.now().isoformat()
        })
        
except Exception as e:
    return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

# 两种获取Checkpoint的方法

### 🔥 **方法一：直接Redis访问**

就是我们之前使用的方法，直接查询Redis键：

```python
# 直接Redis查询
pattern = f"checkpoint:{thread_id}:*"
keys = redis_client.keys(pattern)
latest_key = sorted(keys)[-1]
checkpoint_data = redis_client.get(latest_key)
```

### 🚀 **方法二：使用LangGraph API**

使用官方的Redis Checkpoint Saver API：## 📊 **两种方法对比**

### **方法一：直接Redis访问**

✅ **优点**：

- 更直接，性能稍快
- 完全控制数据格式
- 不依赖LangGraph版本

❌ **缺点**：

- 需要了解Redis键名格式

  - ```
    checkpoint:wang1:20250729235038043:__empty__:1f06c943-fd28-6539-801f-41a94c25bd43
    ```

- 硬编码依赖具体实现

- 升级时可能出问题

### **方法二：LangGraph API** ⭐ **推荐**

✅ **优点**：

- 官方API，更稳定可靠
- 自动处理索引和版本兼容
- 标准化的CheckpointTuple对象
- 支持异步操作

❌ **缺点**：

- 需要安装`langgraph-checkpoint-redis`包
- 稍微多一点的API调用开销

## 🔧 **关键API使用**

基于搜索结果，官方Redis Checkpointer的核心方法：

```python
# 同步版本
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver.from_conn_string("redis://localhost:6379")
checkpointer.setup()  # 重要：创建索引

# 获取最新checkpoint
read_config = {"configurable": {"thread_id": "your_thread_id"}}
checkpoint_tuple = checkpointer.get_tuple(read_config)

# 异步版本  
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

async with AsyncRedisSaver.from_conn_string("redis://localhost:6379") as checkpointer:
    await checkpointer.asetup()
    checkpoint_tuple = await checkpointer.aget_tuple(read_config)
```

## 💡 **建议**

我建议使用**方法二（LangGraph API）**，因为：

1. 这是官方推荐方式，更可靠

2. 自动处理版本兼容性问题

3. 提供标准化的数据结构

4. 您的代码会更加健壮和可维护

   

   

   ### 方法二参考代码

```python
from flask import Flask, jsonify
from langgraph.checkpoint.redis import RedisSaver
from datetime import datetime
import asyncio

app = Flask(__name__)

# 初始化Redis Checkpointer
checkpointer = RedisSaver.from_conn_string("redis://localhost:6379")
checkpointer.setup()  # 创建必要的索引

# 简单的节点状态映射
NODE_STATUS = {
    "__start__": {"name": "开始", "icon": "🚀"},
    "agent": {"name": "AI思考中", "icon": "🤖"},
    "prepare_tool_input": {"name": "准备工具", "icon": "🔧"},
    "tools": {"name": "执行查询", "icon": "⚙️"},
    "update_state_after_tool": {"name": "处理结果", "icon": "🔄"},  
    "format_final_response": {"name": "生成回答", "icon": "📝"},
    "__end__": {"name": "完成", "icon": "✅"}
}

@app.route('/api/status/<thread_id>')
def get_status(thread_id):
    try:
        # 使用LangGraph API获取最新checkpoint
        read_config = {"configurable": {"thread_id": thread_id}}
        
        # 获取最新的checkpoint tuple
        checkpoint_tuple = checkpointer.get_tuple(read_config)
        
        if not checkpoint_tuple:
            return jsonify({"error": "未找到执行线程"}), 404
        
        # 从checkpoint中提取状态信息
        checkpoint = checkpoint_tuple.checkpoint
        
        # 获取suggested_next_step (这里需要根据实际的checkpoint结构调整)
        # 通常在channel_values中或者通过分析当前状态推断
        channel_values = checkpoint.get('channel_values', {})
        
        # 根据您的实际LangGraph实现，suggested_next_step可能在不同位置
        # 这里提供几种可能的获取方式：
        
        # 方式1: 直接从channel_values获取
        suggested_next_step = channel_values.get('suggested_next_step', '')
        
        # 方式2: 从其他可能的位置获取
        if not suggested_next_step:
            # 可能在metadata中
            metadata = checkpoint_tuple.metadata or {}
            suggested_next_step = metadata.get('suggested_next_step', '')
        
        # 方式3: 根据当前节点状态推断下一步
        if not suggested_next_step:
            current_node = channel_values.get('current_node', '')
            # 根据业务逻辑推断下一步...
        
        # 判断是否完成
        is_completed = (not suggested_next_step or 
                       suggested_next_step == "__end__" or
                       channel_values.get('status') == 'completed')
        
        if is_completed:
            return jsonify({
                "status": "completed", 
                "name": "完成",
                "icon": "✅",
                "timestamp": datetime.now().isoformat()
            })
        else:
            # 获取当前步骤信息
            node_info = NODE_STATUS.get(suggested_next_step, {
                "name": "执行中",
                "icon": "⚙️"
            })
            
            return jsonify({
                "status": "running",
                "name": node_info["name"],
                "icon": node_info["icon"], 
                "timestamp": datetime.now().isoformat()
            })
            
    except Exception as e:
        return jsonify({"error": f"获取状态失败: {str(e)}"}), 500

# 异步版本 (如果需要)
@app.route('/api/status-async/<thread_id>')
def get_status_async(thread_id):
    try:
        # 使用异步API
        async def _get_async_status():
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver
            
            async with AsyncRedisSaver.from_conn_string("redis://localhost:6379") as async_checkpointer:
                await async_checkpointer.asetup()
                
                read_config = {"configurable": {"thread_id": thread_id}}
                checkpoint_tuple = await async_checkpointer.aget_tuple(read_config)
                
                if not checkpoint_tuple:
                    return None
                    
                return checkpoint_tuple.checkpoint
        
        # 在Flask中运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            checkpoint = loop.run_until_complete(_get_async_status())
            if not checkpoint:
                return jsonify({"error": "未找到执行线程"}), 404
            
            # 处理checkpoint数据...
            # (相同的逻辑)
            
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/health')
def health_check():
    """健康检查"""
    try:
        # 测试checkpointer连接
        test_config = {"configurable": {"thread_id": "health_check"}}
        checkpointer.get_tuple(test_config)  # 这不会报错，即使没有数据
        
        return jsonify({
            "status": "healthy",
            "checkpointer": "connected",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```



## Checkpoint在Redis中的存储的值

### key: 

```
checkpoint:wang1:20250729235038043:__empty__:1f06c943-fd28-6539-801f-41a94c25bd43
```

其中“wang1:20250729235038043”就是thread_id，它是由 {user_id}:{时间戳}组成的。

### value:

```json
              {
                      "type": "ai",
                      "content": "系统中档口最多的服务区是**南城服务区**，共拥有**39个档口**。该结果通过统计各服务区内未删除档口的数量并按降序排列得出，已通过系统验证确保数据准确性。"
                    }
                  ],
                  "question": "请问这个服务区有几个餐饮档口？"
                },
                "id": "call_498bcec43e2c4b3499e6e1"
              },
              {
                "name": "",
                "args": {
                  
                },
                "id": "call_f71ffe8603ed42da879a17",
                "type": "tool_call"
              }
            ],
            "invalid_tool_calls": []
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "ToolMessage"
          ],
          "kwargs": {
            "content": "SELECT COUNT(*) AS 餐饮档口数量 \nFROM bss_branch b \nJOIN bss_service_area sa ON b.service_area_id = sa.id \nWHERE sa.service_area_name = '南城服务区' \nAND b.classify = '餐饮' \nAND b.delete_ts IS NULL \nAND sa.delete_ts IS NULL;",
            "type": "tool",
            "name": "generate_sql",
            "id": "3dfacea1-93af-444c-bfb4-2995f336f274",
            "tool_call_id": "call_498bcec43e2c4b3499e6e1",
            "status": "success"
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "ToolMessage"
          ],
          "kwargs": {
            "content": "Error:  is not a valid tool, try one of [generate_sql, valid_sql, run_sql].",
            "type": "tool",
            "name": "",
            "id": "1763e2eb-7be4-4e7e-bae3-19f9e0b1b4b5",
            "tool_call_id": "call_f71ffe8603ed42da879a17",
            "status": "error"
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "AIMessage"
          ],
          "kwargs": {
            "content": "",
            "additional_kwargs": {
              "tool_calls": [
                {
                  "index": 0,
                  "id": "call_09fe3a57143947e5b85766",
                  "function": {
                    "arguments": "{\"history_messages\": [{\"type\": \"human\", \"content\": \"请问系统中哪个服务区档口最多？\"}, {\"type\": \"ai\", \"content\": \"系统中档口最多的服务区是**南城服务区**，共拥有**39个档口**。该结果通过统计各服务区内未删除档口的数量并按降序排列得出，已通过系统验证确保数据准确性。\"}], \"question\": \"请问这个服务区有几个餐饮档口？\"}",
                    "name": "generate_sql"
                  },
                  "type": "function"
                }
              ]
            },
            "response_metadata": {
              "finish_reason": "tool_calls",
              "model_name": "qwen3-235b-a22b"
            },
            "type": "ai",
            "id": "run--d61425aa-94cf-4e0c-837a-9ac7c48f4930-0",
            "tool_calls": [
              {
                "name": "generate_sql",
                "args": {
                  "history_messages": [
                    {
                      "type": "human",
                      "content": "请问系统中哪个服务区档口最多？"
                    },
                    {
                      "type": "ai",
                      "content": "系统中档口最多的服务区是**南城服务区**，共拥有**39个档口**。该结果通过统计各服务区内未删除档口的数量并按降序排列得出，已通过系统验证确保数据准确性。"
                    }
                  ],
                  "question": "请问这个服务区有几个餐饮档口？"
                },
                "id": "call_09fe3a57143947e5b85766"
              }
            ],
            "invalid_tool_calls": []
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "ToolMessage"
          ],
          "kwargs": {
            "content": "SELECT COUNT(*) AS 餐饮档口数量 FROM bss_branch b JOIN bss_service_area sa ON b.service_area_id = sa.id WHERE sa.service_area_name = '南城服务区' AND b.classify = '餐饮' AND b.delete_ts IS NULL;",
            "type": "tool",
            "name": "generate_sql",
            "id": "8016bd5b-9ad7-43b3-90f2-1994b798b06b",
            "tool_call_id": "call_09fe3a57143947e5b85766",
            "status": "success"
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "AIMessage"
          ],
          "kwargs": {
            "content": "",
            "additional_kwargs": {
              "tool_calls": [
                {
                  "index": 0,
                  "id": "call_0753617fb1174fab9074eb",
                  "function": {
                    "arguments": "{\"sql\": \"SELECT COUNT(*) AS \\u9910\\u996e\\u6863\\u53e3\\u6570\\u91cf \\nFROM bss_branch b \\nJOIN bss_service_area sa ON b.service_area_id = sa.id \\nWHERE sa.service_area_name = '南城服务区' \\nAND b.classify = '餐饮' \\nAND b.delete_ts IS NULL;\", \"question\": \"\\u8bf7\\u95ee\\u8fd9\\u4e2a\\u670d\\u52a1\\u533a\\u6709\\u51e0\\u4e2a\\u9910\\u996e\\u6863\\u53e3\\uff1f\"}",
                    "name": "valid_sql"
                  },
                  "type": "function"
                }
              ]
            },
            "response_metadata": {
              "finish_reason": "tool_calls",
              "model_name": "qwen3-235b-a22b"
            },
            "type": "ai",
            "id": "run--4c0c02fa-efbb-4cd6-96c0-d80392c99aa9-0",
            "tool_calls": [
              {
                "name": "valid_sql",
                "args": {
                  "sql": "SELECT COUNT(*) AS 餐饮档口数量 \nFROM bss_branch b \nJOIN bss_service_area sa ON b.service_area_id = sa.id \nWHERE sa.service_area_name = '南城服务区' \nAND b.classify = '餐饮' \nAND b.delete_ts IS NULL;",
                  "question": "请问这个服务区有几个餐饮档口？"
                },
                "id": "call_0753617fb1174fab9074eb",
                "type": "tool_call"
              }
            ],
            "invalid_tool_calls": []
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "ToolMessage"
          ],
          "kwargs": {
            "content": "SQL验证通过：语法正确且字段存在",
            "type": "tool",
            "name": "valid_sql",
            "id": "62bde32c-02a9-4e36-aa76-5387cb03ce65",
            "tool_call_id": "call_0753617fb1174fab9074eb",
            "status": "success"
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "AIMessage"
          ],
          "kwargs": {
            "content": "",
            "additional_kwargs": {
              "tool_calls": [
                {
                  "index": 0,
                  "id": "call_b0600de998f5467d96a3f2",
                  "function": {
                    "arguments": "{\"sql\": \"SELECT COUNT(*) AS \\u9910\\u996e\\u6863\\u53e3\\u6570\\u91cf \\nFROM bss_branch b \\nJOIN bss_service_area sa ON b.service_area_id = sa.id \\nWHERE sa.service_area_name = '\\u5357\\u57ce\\u670d\\u52a1\\u533a' \\nAND b.classify = '\\u9910\\u996e' \\nAND b.delete_ts IS NULL;\", \"question\": \"\\u8bf7\\u95ee\\u8fd9\\u4e2a\\u670d\\u52a1\\u533a\\u6709\\u51e0\\u4e2a\\u9910\\u996e\\u6863\\u53e3\\uff1f\"}",
                    "name": "run_sql"
                  },
                  "type": "function"
                }
              ]
            },
            "response_metadata": {
              "finish_reason": "tool_calls",
              "model_name": "qwen3-235b-a22b"
            },
            "type": "ai",
            "id": "run--6144e643-450a-4ec2-932a-230f666dd90c-0",
            "tool_calls": [
              {
                "name": "run_sql",
                "args": {
                  "sql": "SELECT COUNT(*) AS 餐饮档口数量 \nFROM bss_branch b \nJOIN bss_service_area sa ON b.service_area_id = sa.id \nWHERE sa.service_area_name = '南城服务区' \nAND b.classify = '餐饮' \nAND b.delete_ts IS NULL;",
                  "question": "请问这个服务区有几个餐饮档口？"
                },
                "id": "call_b0600de998f5467d96a3f2",
                "type": "tool_call"
              }
            ],
            "invalid_tool_calls": []
          }
        },
        {
          "lc": 1,
          "type": "constructor",
          "id": [
            "langchain",
            "schema",
            "messages",
            "ToolMessage"
          ],
          "kwargs": {
            "content": "[{\"\\u9910\\u996e\\u6863\\u53e3\\u6570\\u91cf\":6}]",
            "type": "tool",
            "name": "run_sql",
            "id": "488da67c-ea4f-46f4-a201-d1bb40c25931",
            "tool_call_id": "call_b0600de998f5467d96a3f2",
            "status": "success"
          }
        }
      ],
      "user_id": "wang1",
      "thread_id": "wang1:20250729235038043",
      "suggested_next_step": "summarize_final_answer",
      "branch:to:agent": null
    },
    "channel_versions": {
      "__start__": "00000000000000000000000000000018.0.2372340570136553",
      "messages": "00000000000000000000000000000033.0.3402020632542543",
      "user_id": "00000000000000000000000000000018.0.6157289048059329",
      "thread_id": "00000000000000000000000000000018.0.3438965440425772",
      "suggested_next_step": "00000000000000000000000000000034.0.4358036384739292",
      "branch:to:agent": "00000000000000000000000000000034.0.30470240061347376",
      "branch:to:prepare_tool_input": "00000000000000000000000000000032.0.683834676177241",
      "branch:to:tools": "00000000000000000000000000000033.0.4617350256378949",
      "branch:to:update_state_after_tool": "00000000000000000000000000000034.0.7301276046246093",
      "branch:to:format_final_response": "00000000000000000000000000000016.0.4685210381789543"
    },
    "
```

