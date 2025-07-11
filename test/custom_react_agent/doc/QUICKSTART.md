# Custom React Agent - 快速开始指南

## 🚀 5分钟快速启动

### 1. 启动API服务
```bash
cd test/custom_react_agent
python api.py
```

服务将在 http://localhost:8000 启动

### 2. 验证服务状态
```bash
curl http://localhost:8000/health
```

### 3. 开始对话
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "请问哪个高速服务区的档口数量最多？", "user_id": "doudou"}'
```

### 4. 查看对话历史 ⭐ 新功能
```bash
# 查看用户的对话列表
curl "http://localhost:8000/api/users/doudou/conversations?limit=5"

# 查看特定对话的详细内容
curl "http://localhost:8000/api/users/doudou/conversations/doudou:20250115103000001"
```

## 📋 基本API用法

### 智能问答
```bash
# 普通对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "你好", "user_id": "alice"}'

# SQL查询
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "查询收入最高的服务区", "user_id": "alice"}'

# 继续对话 (使用相同thread_id)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "详细说明一下", "user_id": "alice", "thread_id": "alice:20250115103000001"}'
```

### 对话历史管理 ⭐ 新功能
```bash
# 获取用户对话列表
curl "http://localhost:8000/api/users/alice/conversations"

# 限制返回数量
curl "http://localhost:8000/api/users/alice/conversations?limit=10"

# 获取特定对话详情
curl "http://localhost:8000/api/users/alice/conversations/alice:20250115103000001"
```

## 💻 Python 客户端示例

### 基础对话
```python
import requests

def chat_with_agent(question, user_id, thread_id=None):
    url = "http://localhost:8000/api/chat"
    payload = {
        "question": question,
        "user_id": user_id
    }
    if thread_id:
        payload["thread_id"] = thread_id
    
    response = requests.post(url, json=payload)
    return response.json()

# 使用示例
result = chat_with_agent("请问服务区数据查询", "alice")
print(f"回答: {result['data']['response']}")
```

### 对话历史查询 ⭐ 新功能
```python
import requests

def get_user_conversations(user_id, limit=10):
    """获取用户对话列表"""
    url = f"http://localhost:8000/api/users/{user_id}/conversations"
    params = {"limit": limit}
    
    response = requests.get(url, params=params)
    return response.json()

def get_conversation_detail(user_id, thread_id):
    """获取对话详情"""
    url = f"http://localhost:8000/api/users/{user_id}/conversations/{thread_id}"
    
    response = requests.get(url)
    return response.json()

# 使用示例
conversations = get_user_conversations("alice", limit=5)
print(f"找到 {len(conversations['data']['conversations'])} 个对话")

if conversations['data']['conversations']:
    thread_id = conversations['data']['conversations'][0]['thread_id']
    detail = get_conversation_detail("alice", thread_id)
    print(f"对话包含 {detail['data']['message_count']} 条消息")
```

## 🌐 JavaScript/前端示例

### 基础对话
```javascript
async function chatWithAgent(question, userId, threadId = null) {
    const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question: question,
            user_id: userId,
            ...(threadId && { thread_id: threadId })
        })
    });
    
    return await response.json();
}

// 使用示例
const result = await chatWithAgent("查询服务区信息", "alice");
console.log("回答:", result.data.response);
```

### 对话历史管理 ⭐ 新功能
```javascript
async function getUserConversations(userId, limit = 10) {
    const response = await fetch(
        `http://localhost:8000/api/users/${userId}/conversations?limit=${limit}`
    );
    return await response.json();
}

async function getConversationDetail(userId, threadId) {
    const response = await fetch(
        `http://localhost:8000/api/users/${userId}/conversations/${threadId}`
    );
    return await response.json();
}

// 使用示例
const conversations = await getUserConversations("alice", 5);
console.log(`找到 ${conversations.data.conversations.length} 个对话`);

if (conversations.data.conversations.length > 0) {
    const firstConv = conversations.data.conversations[0];
    const detail = await getConversationDetail("alice", firstConv.thread_id);
    console.log(`对话详情:`, detail.data);
}
```

## 🧪 测试工具

### 运行完整测试
```bash
cd test/custom_react_agent
python test_api.py
```

### 测试新的对话历史功能 ⭐
```bash
cd test/custom_react_agent
python test_conversation_api.py
```

### 单独测试问题
```bash
python test_api.py "查询服务区收入排名"
```

## 🎯 典型应用场景

### 1. 聊天机器人界面
```python
# 获取用户的历史对话，显示对话列表
conversations = get_user_conversations("user123", limit=20)

for conv in conversations['data']['conversations']:
    print(f"[{conv['formatted_time']}] {conv['conversation_preview']}")
```

### 2. 客服系统
```python
# 客服查看用户的完整对话历史
user_id = "customer_456"
conversations = get_user_conversations(user_id)

for conv in conversations['data']['conversations']:
    thread_id = conv['thread_id']
    detail = get_conversation_detail(user_id, thread_id)
    
    print(f"对话时间: {conv['formatted_time']}")
    print(f"消息数量: {detail['data']['message_count']}")
    # 显示详细消息...
```

### 3. 对话分析
```python
# 分析用户的对话模式
conversations = get_user_conversations("analyst_user")

total_messages = sum(conv['message_count'] for conv in conversations['data']['conversations'])
avg_messages = total_messages / len(conversations['data']['conversations'])

print(f"平均每个对话 {avg_messages:.1f} 条消息")
```

## 🔧 Thread ID 设计说明

### 格式规则
- **格式**: `{user_id}:{timestamp}`
- **示例**: `doudou:20250115103000001`
- **优势**: 
  - 自然包含用户信息
  - 支持时间排序
  - 无需额外映射表

### 时间戳格式
```
20250115103000001
│  │  │ │ │ │ │
│  │  │ │ │ │ └── 毫秒 (001)
│  │  │ │ │ └──── 秒 (30)
│  │  │ │ └────── 分钟 (30)
│  │  │ └──────── 小时 (10)
│  │  └────────── 日 (15)
│  └───────────── 月 (01)
└─────────────── 年 (2025)
```

## ⚠️ 注意事项

1. **服务依赖**: 确保Redis服务可用
2. **数据库连接**: 确认业务数据库连接正常
3. **并发限制**: API有并发和频率限制
4. **数据安全**: 生产环境需要添加认证授权
5. **监控日志**: 注意观察API日志和性能指标

## 🔍 故障排除

### 常见问题
```bash
# 检查服务状态
curl http://localhost:8000/health

# 查看详细日志
python api.py  # 查看启动日志

# 测试基础功能
python test_api.py "你好"

# 测试新功能
python test_conversation_api.py
```

### 性能优化
- 对话列表查询使用Redis SCAN，支持大量数据
- 合理设置limit参数避免过大响应
- 生产环境建议添加缓存层

---

🎉 现在你已经掌握了Custom React Agent API的基本用法和新的对话历史管理功能！

📚 更多详细信息请参考: [完整API文档](./README_API.md) 