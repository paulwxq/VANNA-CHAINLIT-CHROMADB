# Database节点重构概要设计文档

## 🎯 重构目标

将当前的 `_agent_database_node` 拆分为两个独立节点，实现SQL生成验证与执行的分离，提供中间路由能力，提升系统的智能性和用户体验。

## 📋 整体架构变更

### **重构前架构**
```
classify_question → agent_database → format_response → END
                    (generate_sql + execute_sql + summary)
```

### **重构后架构**
```
classify_question → agent_sql_generation_node → agent_sql_execution_node → format_response → END
                    (generate_sql + validation)    (execute_sql + summary)
                           ↓ (失败路由)
                    format_response → END
```

## 🔧 节点详细设计

### **1. _agent_sql_generation_node (SQL生成验证节点)**

#### **功能职责**
- 调用 `generate_sql()` 工具生成SQL
- 使用复用schema_tools的验证逻辑进行SQL验证
- 根据验证结果决定路由方向

#### **核心逻辑**
```python
def _agent_sql_generation_node(self, state: AgentState) -> AgentState:
    """SQL生成验证节点"""
    try:
        question = state["question"]
        
        # 步骤1: SQL生成
        sql_result = generate_sql(question, allow_llm_to_see_data=True)
        
        if not sql_result.get("success"):
            # SQL生成失败处理
            return self._handle_sql_generation_failure(state, sql_result)
        
        sql = sql_result.get("sql")
        state["sql"] = sql
        
        # 步骤2: SQL验证 (如果启用)
        if self._is_sql_validation_enabled():
            validation_result = await self._validate_sql_with_schema_tools(sql)
            
            if not validation_result.get("valid"):
                # 验证失败，尝试修复
                return await self._handle_sql_validation_failure(state, sql, validation_result)
        
        # 生成和验证都成功
        state["sql_generation_success"] = True
        state["execution_path"].append("agent_sql_generation")
        return state
        
    except Exception as e:
        state["error"] = f"SQL生成节点异常: {str(e)}"
        return state
```

#### **SQL验证集成 (复用schema_tools)**
```python
async def _validate_sql_with_schema_tools(self, sql: str) -> Dict[str, Any]:
    """复用schema_tools的SQL验证逻辑"""
    try:
        # 1. 语法验证 (EXPLAIN SQL)
        syntax_valid = await self._validate_sql_syntax(sql)
        if not syntax_valid.get("valid"):
            return {
                "valid": False,
                "error_type": "syntax_error",
                "error_message": syntax_valid.get("error"),
                "can_repair": True
            }
        
        # 2. 禁止词检查
        forbidden_check = self._check_forbidden_keywords(sql)
        if not forbidden_check.get("valid"):
            return {
                "valid": False,
                "error_type": "forbidden_keywords",
                "error_message": forbidden_check.get("error"),
                "can_repair": False
            }
        
        return {"valid": True}
        
    except Exception as e:
        return {
            "valid": False,
            "error_type": "validation_exception",
            "error_message": str(e),
            "can_repair": False
        }

def _check_forbidden_keywords(self, sql: str) -> Dict[str, Any]:
    """检查禁止的SQL关键词"""
    forbidden_keywords = ['UPDATE', 'DELETE', 'DROP', 'ALTER', 'INSERT']
    sql_upper = sql.upper()
    
    for keyword in forbidden_keywords:
        if keyword in sql_upper:
            return {
                "valid": False,
                "error": f"不允许的操作: {keyword}。本系统只支持查询操作(SELECT)。"
            }
    
    return {"valid": True}

async def _validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
    """语法验证 - 复用schema_tools逻辑"""
    try:
        # 获取数据库连接 (复用现有连接逻辑)
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        
        # 执行EXPLAIN验证
        explain_sql = f"EXPLAIN {sql}"
        # 注意: 这里需要适配到实际的数据库连接方式
        result = await vn.run_sql(explain_sql)
        
        return {"valid": True}
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
```

#### **SQL修复逻辑 (复用schema_tools)**
```python
async def _handle_sql_validation_failure(self, state: AgentState, sql: str, validation_result: Dict) -> AgentState:
    """处理SQL验证失败"""
    error_type = validation_result.get("error_type")
    
    # 禁止词错误，直接失败
    if error_type == "forbidden_keywords":
        state["sql_generation_success"] = False
        state["user_prompt"] = validation_result.get("error_message")
        return state
    
    # 语法错误，尝试LLM修复 (只修复一次)
    if error_type == "syntax_error" and self._is_auto_repair_enabled():
        repaired_sql = await self._repair_sql_with_llm(sql, validation_result.get("error_message"))
        
        if repaired_sql:
            # 再次验证修复后的SQL
            revalidation = await self._validate_sql_with_schema_tools(repaired_sql)
            
            if revalidation.get("valid"):
                state["sql"] = repaired_sql
                state["sql_generation_success"] = True
                state["sql_repair_applied"] = True
                return state
    
    # 修复失败或不支持修复
    state["sql_generation_success"] = False
    state["user_prompt"] = f"SQL生成遇到问题: {validation_result.get('error_message')}"
    return state

```python
async def _repair_sql_with_llm(self, sql: str, error_message: str) -> Optional[str]:
    """使用LLM修复SQL - 只尝试一次"""
    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        
        # 构建修复提示词
        repair_prompt = f"""你是一个PostgreSQL SQL专家，请修复以下SQL语句的语法错误。

当前数据库类型: PostgreSQL
错误信息: {error_message}

需要修复的SQL:
{sql}

修复要求:
1. 只修复语法错误和表结构错误
2. 保持SQL的原始业务逻辑不变  
3. 使用PostgreSQL标准语法
4. 确保修复后的SQL语法正确

请直接输出修复后的SQL语句，不要添加其他说明文字。"""

        # 调用LLM修复 - 复用schema_tools的异步调用方式
        response = await asyncio.to_thread(
            vn.chat_with_llm,
            question=repair_prompt,
            system_prompt="你是一个专业的PostgreSQL SQL专家，专门负责修复SQL语句中的语法错误。"
        )
        
        if response and response.strip():
            return response.strip()
        
        return None
        
    except Exception as e:
        print(f"[ERROR] SQL修复失败: {str(e)}")
        return None

async def _handle_sql_validation_failure(self, state: AgentState, sql: str, validation_result: Dict) -> AgentState:
    """处理SQL验证失败 - 重要约束：只修复一次"""
    error_type = validation_result.get("error_type")
    
    # 禁止词错误，直接失败，不尝试修复
    if error_type == "forbidden_keywords":
        state["sql_generation_success"] = False
        state["user_prompt"] = validation_result.get("error_message")
        state["execution_path"].append("forbidden_keywords_failed")
        return state
    
    # 语法错误，仅尝试修复一次
    if error_type == "syntax_error" and self._is_auto_repair_enabled():
        print(f"[SQL_REPAIR] 尝试修复SQL语法错误(仅一次): {validation_result.get('error_message')}")
        
        repaired_sql = await self._repair_sql_with_llm(sql, validation_result.get("error_message"))
        
        if repaired_sql:
            # 对修复后的SQL进行验证 - 不管结果如何，不再重试
            revalidation = await self._validate_sql_with_schema_tools(repaired_sql)
            
            if revalidation.get("valid"):
                # 修复成功
                state["sql"] = repaired_sql
                state["sql_generation_success"] = True
                state["sql_repair_applied"] = True
                state["execution_path"].append("sql_repair_success")
                print(f"[SQL_REPAIR] SQL修复成功")
                return state
            else:
                # 修复后仍然失败，直接结束
                print(f"[SQL_REPAIR] 修复后验证仍然失败: {revalidation.get('error_message')}")
                state["sql_generation_success"] = False
                state["user_prompt"] = f"SQL修复尝试失败: {revalidation.get('error_message')}"
                state["execution_path"].append("sql_repair_failed")
                return state
        else:
            # LLM修复失败
            print(f"[SQL_REPAIR] LLM修复调用失败")
            state["sql_generation_success"] = False
            state["user_prompt"] = f"SQL语法修复失败: {validation_result.get('error_message')}"
            state["execution_path"].append("sql_repair_failed")
            return state
    
    # 不启用修复或其他错误类型，直接失败
    state["sql_generation_success"] = False
    state["user_prompt"] = f"SQL验证失败: {validation_result.get('error_message')}"
    state["execution_path"].append("sql_validation_failed")
    return state
```

### **2. _agent_sql_execution_node (SQL执行节点)**

#### **功能职责**
- 执行已验证的SQL语句
- 根据配置决定是否生成摘要
- 保持原有的执行逻辑

#### **核心逻辑**
```python
def _agent_sql_execution_node(self, state: AgentState) -> AgentState:
    """SQL执行节点 - 保持原有逻辑"""
    try:
        sql = state.get("sql")
        question = state["question"]
        
        # 步骤1: 执行SQL (复用原有逻辑)
        execute_result = execute_sql.invoke({"sql": sql})
        
        if not execute_result.get("success"):
            state["error"] = execute_result.get("error", "SQL执行失败")
            return state
        
        query_result = execute_result.get("data_result")
        state["query_result"] = query_result
        
        # 步骤2: 生成摘要 (根据配置)
        if self._should_generate_summary(query_result):
            original_question = self._extract_original_question(question)
            
            summary_result = generate_summary.invoke({
                "question": original_question,
                "query_result": query_result,
                "sql": sql
            })
            
            if summary_result.get("success"):
                state["summary"] = summary_result.get("summary")
            else:
                # 摘要生成失败不是致命错误
                state["summary"] = f"查询执行完成，共返回 {query_result.get('row_count', 0)} 条记录。"
        
        state["execution_path"].append("agent_sql_execution")
        return state
        
    except Exception as e:
        state["error"] = f"SQL执行节点异常: {str(e)}"
        return state

def _should_generate_summary(self, query_result: Dict) -> bool:
    """判断是否应该生成摘要"""
    from app_config import ENABLE_RESULT_SUMMARY
    return ENABLE_RESULT_SUMMARY and query_result.get('row_count', 0) > 0
```

## 🔀 条件路由设计

### **SQL生成节点的条件路由**
```python
def _route_after_sql_generation(self, state: AgentState) -> Literal["continue_execution", "return_to_user"]:
    """SQL生成后的路由决策"""
    
    if state.get("sql_generation_success"):
        return "continue_execution"  # 路由到SQL执行节点
    else:
        return "return_to_user"      # 路由到format_response，结束流程
```

### **工作流配置更新**
```python
def _create_workflow(self, routing_mode: str = None) -> StateGraph:
    """更新工作流创建逻辑"""
    workflow = StateGraph(AgentState)
    
    # 添加新的节点
    workflow.add_node("classify_question", self._classify_question_node)
    workflow.add_node("agent_sql_generation", self._agent_sql_generation_node)
    workflow.add_node("agent_sql_execution", self._agent_sql_execution_node)
    workflow.add_node("agent_chat", self._agent_chat_node)
    workflow.add_node("format_response", self._format_response_node)
    
    # 设置条件路由
    workflow.add_conditional_edges(
        "classify_question",
        self._route_after_classification,
        {
            "DATABASE": "agent_sql_generation",
            "CHAT": "agent_chat"
        }
    )
    
    # SQL生成后的条件路由
    workflow.add_conditional_edges(
        "agent_sql_generation",
        self._route_after_sql_generation,
        {
            "continue_execution": "agent_sql_execution",
            "return_to_user": "format_response"
        }
    )
    
    # 普通边缘
    workflow.add_edge("agent_sql_execution", "format_response")
    workflow.add_edge("agent_chat", "format_response")
    workflow.add_edge("format_response", END)
    
    return workflow.compile()
```

## ⚙️ 配置参数设计

### **新增配置参数 - 精简版**
```python
# 在app_config.py中添加
SQL_VALIDATION_CONFIG = {
    "enable_syntax_validation": True,      # 是否启用语法验证(EXPLAIN SQL)
    "enable_forbidden_check": True,       # 是否启用禁止词检查  
    "enable_auto_repair": True,           # 是否启用自动修复(只尝试一次)
}

# 现有配置保持不变
ENABLE_RESULT_SUMMARY = True  # 控制摘要生成
```

### **配置使用逻辑 - 明确约束**
```python
def _is_sql_validation_enabled(self) -> bool:
    """检查是否启用SQL验证"""
    # 注意：任一验证功能启用都算启用验证
    return (SQL_VALIDATION_CONFIG.get("enable_syntax_validation", False) or 
            SQL_VALIDATION_CONFIG.get("enable_forbidden_check", False))

def _is_auto_repair_enabled(self) -> bool:
    """检查是否启用自动修复"""
    # 只有在语法验证启用的情况下，自动修复才有意义
    return (SQL_VALIDATION_CONFIG.get("enable_auto_repair", False) and 
            SQL_VALIDATION_CONFIG.get("enable_syntax_validation", False))

def _should_skip_validation(self) -> bool:
    """判断是否跳过所有验证"""
    # 当所有验证功能都禁用时，跳过验证步骤
    return not self._is_sql_validation_enabled()
```

### **验证策略的完整逻辑**
```python
# 验证流程的完整决策树
if not self._is_sql_validation_enabled():
    # 跳过所有验证，直接使用生成的SQL
    pass
else:
    # 按优先级执行验证
    if SQL_VALIDATION_CONFIG.get("enable_syntax_validation"):
        # 1. 语法验证 (EXPLAIN SQL)
        syntax_result = await self._validate_sql_syntax(sql)
        if not syntax_result.valid and self._is_auto_repair_enabled():
            # 尝试修复 (只一次)
            repaired_sql = await self._repair_sql_with_llm(sql, syntax_result.error)
            # 修复后不管成功失败，都不再重试
    
    if SQL_VALIDATION_CONFIG.get("enable_forbidden_check"):
        # 2. 禁止词检查 (不可修复)
        forbidden_result = self._check_forbidden_keywords(sql)
        if not forbidden_result.valid:
            # 直接失败，不尝试修复
            return self._handle_forbidden_keywords_error(state, forbidden_result)
```

## 📊 状态字段更新

### **AgentState新增字段**
```python
class AgentState(TypedDict):
    # 现有字段保持不变...
    
    # 新增字段
    sql_generation_success: bool           # SQL生成是否成功
    sql_repair_applied: bool              # 是否应用了SQL修复
    user_prompt: Optional[str]            # 给用户的提示信息
```

## 🔄 错误处理和用户提示

### **SQL生成失败的情况处理**
```python
```python
def _handle_sql_generation_failure(self, state: AgentState, sql_result: Dict) -> AgentState:
    """处理SQL生成失败 - 统一处理三种情况"""
    error_message = sql_result.get("error", "")
    error_type = sql_result.get("error_type", "")
    
    # 重要设计决策：不进行二次分类判断，统一按数据库问题处理
    # 原因：第一次LLM分类已经判断为DATABASE，第二次大概率仍是DATABASE
    
    # 根据错误类型和内容生成统一的用户提示
    if "no relevant tables" in error_message.lower() or "table not found" in error_message.lower():
        # 情况1：数据库缺少表/字段
        user_prompt = "数据库中没有相关的表或字段信息，请您提供更多具体信息或修改问题。"
        failure_reason = "missing_database_info"
    elif "ambiguous" in error_message.lower() or "more information" in error_message.lower():
        # 情况2：问题太模糊  
        user_prompt = "您的问题需要更多信息才能准确查询，请提供更详细的描述。"
        failure_reason = "ambiguous_question"
    elif error_type == "llm_explanation":
        # 情况3：LLM返回解释性文本而非SQL
        user_prompt = error_message + " 请尝试重新描述您的问题或询问其他内容。"
        failure_reason = "llm_explanation"
    else:
        # 其他未分类的失败情况
        user_prompt = "无法生成有效的SQL查询，请尝试重新描述您的问题。"
        failure_reason = "unknown_generation_failure"
    
    # 关键决策：所有失败都返回用户提示，不路由到CHAT
    state["sql_generation_success"] = False
    state["user_prompt"] = user_prompt
    state["sql_generation_failure_reason"] = failure_reason
    state["execution_path"].append("sql_generation_failed")
    
    print(f"[SQL_GENERATION] 生成失败: {failure_reason} - {user_prompt}")
    return state
```

### **format_response节点的适配**
```python
def _format_response_node(self, state: AgentState) -> AgentState:
    """格式化响应节点 - 适配新的失败处理"""
    
    # 处理SQL生成失败的情况
    if not state.get("sql_generation_success", True) and state.get("user_prompt"):
        state["final_response"] = {
            "success": False,
            "response": state["user_prompt"],
            "type": "DATABASE",
            "sql_generation_failed": True,
            "execution_path": state["execution_path"],
            "classification_info": {
                "confidence": state.get("classification_confidence", 0),
                "reason": state.get("classification_reason", ""),
                "method": state.get("classification_method", "")
            }
        }
        return state
    
    # 其他情况保持原有逻辑
    # ... (原有的format_response逻辑)
```

## 🚀 实施计划

### **阶段1: 基础重构**
1. 创建 `_agent_sql_generation_node` 节点
2. 创建 `_agent_sql_execution_node` 节点  
3. 更新工作流配置和条件路由
4. 基础功能测试

### **阶段2: 验证集成**
1. 集成schema_tools的SQL验证逻辑
2. 实现SQL修复功能
3. 添加配置参数控制
4. 验证功能测试

### **阶段3: 错误处理优化**
1. 完善错误分类和用户提示
2. 优化format_response节点适配
3. 用户体验测试和优化

### **阶段4: 全面测试**
1. 各种路由模式兼容性测试
2. 边界情况和异常处理测试
3. 性能和稳定性测试

## 🔍 重要设计细节和约束

### **SQL修复的执行限制**
- **修复次数限制**：SQL语法修复只执行一次，不进行多次重试
- **修复范围限制**：只修复语法错误和表结构错误，不修改业务逻辑
- **修复失败处理**：如果修复后仍无法通过验证，直接返回错误给用户

### **验证流程的优先级**
1. **语法验证优先**：先进行EXPLAIN SQL验证
2. **禁止词检查**：通过语法验证后检查禁止的操作词
3. **修复策略**：只对语法错误尝试修复，禁止词错误直接失败

### **错误处理的统一策略**
- **三种失败情况合并处理**：数据库缺少表/字段、问题模糊、无法判定都统一返回用户提示
- **不进行二次分类**：坚持第一次分类结果，不因SQL生成失败而重新路由到CHAT
- **提示信息明确**：根据具体错误原因给出针对性的用户指导

### **配置参数的作用范围**
- **验证开关独立**：语法验证和禁止词检查可独立控制
- **修复功能可选**：可以只验证不修复，由配置决定
- **全局生效**：所有路由模式(包括database_direct)都遵循验证配置

### **节点内部处理约束**
- **原子性保证**：每个节点的处理对LangGraph来说是原子的
- **状态完整性**：节点间通过状态传递所有必要信息
- **错误不中断流程**：验证或修复失败不抛异常，通过状态标记处理

### **与现有架构的兼容性**
- **工具函数不变**：继续使用现有的@tool装饰的函数
- **状态结构兼容**：新增字段不影响现有状态处理逻辑
- **路由模式兼容**：database_direct、chat_direct、hybrid模式都支持新流程