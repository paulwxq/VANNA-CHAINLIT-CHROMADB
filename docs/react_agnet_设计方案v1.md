## 设计方案

### 我的需求

请遍历知识库的github项目和*.ipynb文件，我想做一个测试： 

1.我要使用langchain/langgraph v0.3.x版本开发一个Agent.
2.这个Agent 拥有三个节点，入口的LLM节点，包含四个tools的节点，end节点。 
a.) 作为入口的LLM， 
b.) 包含四个tools函数： generate_sql()(产生sql)，valid_sql(验证sql)，run_sql(运行sql)，generate_summary()(总结执行结果)。 
c.) 如果无法生成sql，也请LLM返回无法生成SQL的原因。 
3.使用 create_react_agent()，通过langgraph把这三个节点连接在一起。 
4.你可以参考“4. LangGraph 实现自治循环代理（ReAct）及事件流的应用.ipynb”。 
5.如果入口节点判断数据库中的内容无法实现查询，比如是一个“荔枝几月上市”的问题，请用LLM常识来回答。 
我上面的内容只是想做一个测试，请在项目的test目录下，使用 ipynb 来开发。

### **项目结构**：

这是一个 Vanna-Chainlit-Chromadb 项目，已经有完整的结构，包括：

- `test/` 目录已存在，现在我要在test/目录下创建一个`vanna_agent_test.ipynb` 的代码用于测试场景的场景
- 复用已有数据库查询和 LLM 集成的基础设施

### 1. 核心理念

- **所有决策都由 agent LLM 做出**，而不是工具
- **工具只负责执行**，返回执行结果到 state
- **agent LLM 根据 state 中的所有信息智能判断下一步**

#### 架构图（修正版）

```
     ┌──────┐
     │ START│
     └───┬──┘
         │
    ┌────▼────┐
    │  agent  │◄────┐
    └──┬───┬──┘     │
       │   │        │
       │   └─→END   │
       │            │
    ┌──▼──────┐     │
    │  tools  ├─────┘
    └─────────┘
```

agent 节点决定：

- 调用 tools（继续处理）
- 或直接到 END（结束并返回结果）

### 2. 改进的 State 设计

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    # 执行状态记录
    sql_generated: Optional[str]        # 生成的SQL
    sql_validated: Optional[bool]       # 是否通过验证
    sql_executed: Optional[bool]        # 是否执行成功
    query_result: Optional[Any]         # 查询结果
    summary_generated: Optional[str]    # 生成的总结
    
    # 错误信息记录
    sql_generation_error: Optional[str]     # SQL生成错误
    sql_validation_error: Optional[str]     # SQL验证错误
    sql_execution_error: Optional[str]      # SQL执行错误
    summary_generation_error: Optional[str] # 总结生成错误
    
    # 重试计数
    sql_generation_attempts: int
    sql_validation_attempts: int
```

### 3.  Agent 节点（完全由 LLM 决策）

```python
def agent_node(state: AgentState) -> dict:
    """Agent节点：分析当前状态并决定下一步行动"""
    
    system_prompt = """
    你是一个智能SQL查询助手。你有以下四个工具可以调用：
    1. generate_sql: 生成SQL查询语句
    2. valid_sql: 验证SQL语句的正确性
    3. run_sql: 执行SQL查询
    4. generate_summary: 总结查询结果
    
    工具必须按照上述顺序调用。
    
    重要规则：
    - 首先判断用户问题是否需要查询数据库
    - 如果generate_sql失败（返回空或错误），请判断是否为常识问题
    - 如果是常识问题（如"荔枝几月上市"），直接用你的知识回答，不再调用工具
    - 如果valid_sql失败且是语法错误，可以尝试修正后重新生成SQL
    - 如果run_sql失败，判断是否需要重新生成SQL或直接返回错误
    
    当前执行状态：
    - SQL生成: {sql_generated} (错误: {sql_generation_error})
    - SQL验证: {sql_validated} (错误: {sql_validation_error})
    - SQL执行: {sql_executed} (错误: {sql_execution_error})
    - 查询结果: {有结果 if query_result else 无结果}
    - 总结生成: {summary_generated}
    
    请根据当前状态，决定：
    1. 调用哪个工具（或不调用工具）
    2. 如果不调用工具，是直接回答还是返回错误信息
    """
    
    # LLM 分析 state 并决定调用哪个工具或结束
    # 返回的是 LLM 的决策，不是硬编码的逻辑
```

### 4. 工具设计（只返回结果）

**复用项目现有功能**：

```python
# 使用项目中的 vn (Vanna实例)
from core.vanna_llm_factory import get_vn
vn = get_vn()

# 复用现有的验证和总结方法
# vn.validate_sql()
# vn.generate_summary()
```

#### Tools 设计（作为一个统一的 tools 节点）

```python
# tools节点内部根据state.current_tool调用对应的工具
def tools_node(state: AgentState):
    current_tool = state.get("current_tool")
    
    if current_tool == "generate_sql":
        return generate_sql(state)
    elif current_tool == "valid_sql":
        return valid_sql(state)
    elif current_tool == "run_sql":
        return run_sql(state)
    elif current_tool == "generate_summary":
        return generate_summary(state)
```

**创建四个工具函数**：

- 每个工具返回更新后的 state
- 包含详细的错误信息

```python
@tool
def generate_sql(query: str) -> dict:
    """生成SQL语句"""
    try:
        sql = vn.generate_sql(query)
        return {
            "sql": sql,
            "success": bool(sql),
            "error": "无法生成SQL" if not sql else None
        }
    except Exception as e:
        return {
            "sql": None,
            "success": False,
            "error": str(e)
        }

@tool
def valid_sql(sql: str) -> dict:
    """验证SQL语句"""
    try:
        is_valid = vn.validate_sql(sql)
        return {
            "valid": is_valid,
            "success": True,
            "error": "SQL语法错误" if not is_valid else None
        }
    except Exception as e:
        return {
            "valid": False,
            "success": False,
            "error": str(e)
        }

# 其他工具类似...
```

### 5. 条件边逻辑（should_continue）

```python
def should_continue(state: AgentState) -> str:
    """由最后一条消息决定继续还是结束"""
    last_message = state["messages"][-1]
    
    # 如果 LLM 决定调用工具，继续到 tools
    if last_message.tool_calls:
        return "tools"
    
    # 否则结束
    return "end"
```

### 6. 关键改进点

1. **完全由 LLM 智能决策**：
   - 不在 state 中硬编码 next_step
   - LLM 根据所有状态信息自主判断
2. **工具只负责执行**：
   - 工具返回执行结果
   - 不包含任何决策逻辑
3. **更灵活的错误处理**：
   - LLM 可以根据具体错误类型智能处理
   - 支持更复杂的重试逻辑
4. **常识问题判断**：
   - 在提示词中明确：SQL生成失败时要再次判断是否为常识问题
   - LLM 可以直接给出答案

