# Agent配置参数说明

本文档说明了 `agent/config.py` 中配置参数的作用和默认值。

## 配置文件结构

Agent配置采用简单的嵌套字典结构：

```python
AGENT_CONFIG = {
    "classification": {...},      # 问题分类器配置
    "database_agent": {...},      # 数据库Agent配置
    "chat_agent": {...},          # 聊天Agent配置
    "health_check": {...},        # 健康检查配置
    "performance": {...},         # 性能优化配置
}
```

## 详细配置参数说明

### 1. 问题分类器配置 (`classification`)

| 参数名称 | 默认值 | 类型 | 说明 |
|---------|-------|------|------|
| `high_confidence_threshold` | 0.8 | float | **高置信度阈值**：当规则分类置信度 ≥ 此值时，直接使用规则分类结果，不调用LLM二次分类 |
| `low_confidence_threshold` | 0.4 | float | **低置信度阈值**：当规则分类置信度 ≤ 此值时，启用LLM二次分类提升准确性 |

**使用场景说明：**
- 调整 `high_confidence_threshold` 可以控制何时信任规则分类：值越高越保守，更多问题会触发LLM分类
- 调整 `low_confidence_threshold` 可以控制何时使用LLM分类：值越低，越少问题会使用LLM分类
- 中间值(0.4-0.8)的问题直接使用规则分类结果，但置信度相对较低

### 2. 数据库Agent配置 (`database_agent`)

| 参数名称 | 默认值 | 类型 | 说明 |
|---------|-------|------|------|
| `max_iterations` | 5 | int | **最大迭代次数**：Agent工具调用的最大轮数，防止无限循环 |
| `enable_verbose` | True | bool | **详细日志**：是否输出Agent执行的详细日志 |
| `early_stopping_method` | "generate" | string | **早停策略**：Agent的早停方法 |

**典型工作流程：**
```
用户问题 → generate_sql → execute_sql → generate_summary → 返回结果
```

### 3. 聊天Agent配置 (`chat_agent`)

| 参数名称 | 默认值 | 类型 | 说明 |
|---------|-------|------|------|
| `max_iterations` | 3 | int | **最大迭代次数**：聊天Agent的最大工具调用轮数 |
| `enable_verbose` | True | bool | **详细日志**：是否输出Agent执行的详细日志 |
| `enable_context_injection` | True | bool | **上下文注入**：是否将分类原因注入到聊天上下文中 |

**上下文注入示例：**
- 启用时：`"你好，请介绍平台功能\n\n上下文: 分类原因: 匹配聊天关键词: ['你好']"`
- 禁用时：`"你好，请介绍平台功能"`

### 4. 健康检查配置 (`health_check`)

| 参数名称 | 默认值 | 类型 | 说明 |
|---------|-------|------|------|
| `test_question` | "你好" | string | **测试问题**：健康检查使用的标准测试问题 |
| `enable_full_test` | True | bool | **完整测试**：是否执行完整的工作流测试 |

**健康检查级别：**
- **完整测试**：执行真实的问题处理流程，包括分类和Agent调用
- **简单检查**：仅检查组件初始化状态，不执行实际处理

### 5. 性能优化配置 (`performance`)

| 参数名称 | 默认值 | 类型 | 说明 |
|---------|-------|------|------|
| `enable_agent_reuse` | True | bool | **Agent实例重用**：是否预创建并重用Agent实例以提升性能 |

**性能影响：**
- 启用 `enable_agent_reuse`：首次初始化较慢，后续请求快速响应
- 禁用 `enable_agent_reuse`：每次请求都创建新Agent，响应时间较长但内存占用少

## 使用方法

### 获取配置
```python
from agent.config import get_current_config, get_nested_config

# 获取完整配置
config = get_current_config()

# 获取特定配置项
threshold = get_nested_config(config, "classification.high_confidence_threshold", 0.8)
max_iterations = get_nested_config(config, "database_agent.max_iterations", 5)
```

## 配置调优建议

### 分类准确性调优
- **提高分类准确性**：降低 `high_confidence_threshold`，增加LLM分类使用
- **减少LLM调用成本**：提高 `low_confidence_threshold`，减少LLM分类

### 性能调优
- **高并发场景**：启用 `enable_agent_reuse`
- **内存受限场景**：禁用 `enable_agent_reuse`
- **减少Agent调用轮数**：降低 `max_iterations`

## 注意事项

1. **配置兼容性**：配置文件提供回退机制，即使配置文件不可用也能正常工作
2. **参数修改**：修改配置后需要重启应用才能生效
3. **性能监控**：建议监控Agent的响应时间和资源使用情况 