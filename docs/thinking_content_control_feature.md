# Thinking 内容控制功能实现

## 概述

本文档记录了在 API 返回结果中控制 `<think></think>` 内容显示的功能实现。该功能允许通过配置参数 `DISPLAY_SUMMARY_THINKING` 来控制是否在 API 响应的 message 字段中显示 LLM 的思考过程。

## 修改日期

2024年12月（具体日期根据实际情况）

## 问题背景

在使用 `/api/v0/ask` 接口时，当 LLM 无法生成有效 SQL 查询时，会返回包含 `<think></think>` 标签的解释性文本。用户希望能够通过配置参数控制是否显示这些思考内容，与 `generate_summary` 方法中的行为保持一致。

### 问题示例

修改前的 API 返回：
```json
{
    "code": 400,
    "data": {
        "columns": [],
        "conversation_id": null,
        "rows": [],
        "session_id": null,
        "sql": null,
        "summary": null
    },
    "message": "<think>好的，用户现在问的是\"请找出50个vip用户的名称？\"。首先，我需要明确几个问题。表中是否有直接标识VIP用户的信息？根据提供的表结构，bank_churners表里并没有一个字段直接标明客户是VIP用户。现有的字段包括客户的基本信息、交易行为和流失概率等，但没有VIP相关的字段。\n\n接下来，用户可能认为某些信用卡类别或者收入等级较高的客户可以视为VIP。例如，信用卡类型中的Gold或Platinum卡通常被视为高价值客户。但根据提供的card_category字段，示例数据中只有Blue、Gold、Silver三种类型。可能Gold卡的客户被认为是VIP，但需要确认是否Gold卡就是VIP的标准。\n\n此外，用户可能想通过其他指标来定义VIP，比如高收入、高信用额度、高交易额等。比如，income_category中$120K+的客户可能属于高收入群体，或者credit_limit较高的客户。但问题在于，这些都需要业务定义，而当前的上下文并没有给出如何确定VIP的标准。\n\n另外，用户之前的查询历史显示他们关注过交易次数和平均利用率，但这次转向VIP用户，可能需要不同的标准。由于没有明确的VIP字段，可能需要创建一个基于现有字段的筛选条件，比如结合card_category（如Gold卡）、income_category（高收入）、credit_limit（高额度）等。\n\n但根据现有的表结构，无法直接获取VIP用户，因为没有相关字段。所以正确的做法应该是告知用户当前数据不足以回答这个问题，或者需要进一步明确VIP的定义标准。如果用户坚持要找50个VIP客户，可能需要假设某个字段作为VIP的标志，但这样存在风险，因为可能不符合实际业务定义。\n\n因此，根据提供的上下文，无法生成有效的SQL查询，因为没有足够的信息来确定如何识别VIP用户。需要用户提供更多关于VIP的定义，或者检查是否有遗漏的字段。</think>\n\n根据提供的表结构，`bank_churners` 表中没有直接标识 VIP 用户的字段（如 VIP 标签、客户等级等）。要查询 VIP 用户需要额外的定义标准（例如：高收入人群、高信用额度、特定信用卡类别等），但当前上下文未提供相关字段或规则，因此无法直接生成 SQL 查询。\n\n**原因**：表中缺乏明确标识 VIP 用户的字段或筛选条件。",
    "success": false
}
```

## 解决方案

### 1. 配置参数

在 `app_config.py` 中已存在配置参数：

```python
# 是否在摘要中显示thinking过程
# True: 显示 <think></think> 内容
# False: 隐藏 <think></think> 内容，只显示最终答案
DISPLAY_SUMMARY_THINKING = False
```

### 2. 核心函数实现

复用了 `base_llm_chat.py` 中的 `_remove_thinking_content` 函数：

```python
def _remove_thinking_content(text: str) -> str:
    """
    移除文本中的 <think></think> 标签及其内容
    复用自 base_llm_chat.py 中的同名方法
    
    Args:
        text (str): 包含可能的 thinking 标签的文本
        
    Returns:
        str: 移除 thinking 内容后的文本
    """
    if not text:
        return text
    
    # 移除 <think>...</think> 标签及其内容（支持多行）
    # 使用 re.DOTALL 标志使 . 匹配包括换行符在内的任何字符
    cleaned_text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除可能的多余空行
    cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text)
    
    # 去除开头和结尾的空白字符
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text
```

## 修改内容详情

### 1. 文件修改：`citu_app.py`

#### 1.1 导入必要模块

```python
from app_config import API_MAX_RETURN_ROWS, DISPLAY_SUMMARY_THINKING
import re
```

#### 1.2 添加 thinking 内容处理函数

在文件中添加了 `_remove_thinking_content` 函数（复用自 `base_llm_chat.py`）。

#### 1.3 修改 `ask_full` 方法

在两个处理 `last_llm_explanation` 的位置添加了 thinking 内容控制逻辑：

**位置1：正常流程处理**
```python
# 关键：检查是否有LLM解释性文本（无法生成SQL的情况）
if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
    # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
    explanation_message = vn.last_llm_explanation
    if not DISPLAY_SUMMARY_THINKING:
        explanation_message = _remove_thinking_content(explanation_message)
        print(f"[DEBUG] 隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
    
    # 在解释性文本末尾添加提示语
    explanation_message = explanation_message + "请尝试用其它方式提问。"
    
    # 使用 result.failed 返回，success为false，但在message中包含LLM友好的解释
    return jsonify(result.failed(
        message=explanation_message,  # 处理后的解释性文本
        code=400,  # 业务逻辑错误，使用400
        data={
            "sql": None,
            "rows": [],
            "columns": [],
            "summary": None,
            "conversation_id": conversation_id if 'conversation_id' in locals() else None,
            "session_id": browser_session_id
        }
    )), 200  # HTTP状态码仍为200，因为请求本身成功处理了
```

**位置2：异常处理**
```python
# 即使发生异常，也检查是否有业务层面的解释
if hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
    # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
    explanation_message = vn.last_llm_explanation
    if not DISPLAY_SUMMARY_THINKING:
        explanation_message = _remove_thinking_content(explanation_message)
        print(f"[DEBUG] 异常处理中隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
    
    # 在解释性文本末尾添加提示语
    explanation_message = explanation_message + "请尝试用其它方式提问。"
    
    return jsonify(result.failed(
        message=explanation_message,
        code=400,
        data={
            "sql": None,
            "rows": [],
            "columns": [],
            "summary": None,
            "conversation_id": conversation_id if 'conversation_id' in locals() else None,
            "session_id": browser_session_id
        }
    )), 200
```

#### 1.4 修改 `ask_cached` 方法

添加了对 `last_llm_explanation` 的处理逻辑（之前缺失）：

```python
# 检查是否有LLM解释性文本（无法生成SQL的情况）
if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
    # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
    explanation_message = vn.last_llm_explanation
    if not DISPLAY_SUMMARY_THINKING:
        explanation_message = _remove_thinking_content(explanation_message)
        print(f"[DEBUG] ask_cached中隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
    
    # 在解释性文本末尾添加提示语
    explanation_message = explanation_message + "请尝试用其它方式提问。"
    
    return jsonify(result.failed(
        message=explanation_message,
        code=400,
        data={
            "sql": None,
            "rows": [],
            "columns": [],
            "summary": None,
            "conversation_id": conversation_id,
            "session_id": browser_session_id,
            "cached": False
        }
    )), 200
```

## 功能特性

### 1. Thinking 内容控制

- **当 `DISPLAY_SUMMARY_THINKING = True`**：返回完整的 LLM 解释，包括 `<think></think>` 内容
- **当 `DISPLAY_SUMMARY_THINKING = False`**：自动移除 `<think></think>` 标签及其内容，只返回最终的解释文本

### 2. 用户友好提示

在无法生成 SQL 的场景下，会在解释性文本末尾自动添加 "请尝试用其它方式提问。" 提示语。

### 3. 适用场景

该功能仅在以下特定场景下生效：
- 当 LLM 无法生成有效的 SQL 查询时
- 当 LLM 返回解释性文本而不是 SQL 时
- 例如：询问不存在的字段、表结构不支持的查询等

### 4. 不适用场景

以下场景不会应用此功能：
- 正常生成 SQL 并返回数据时
- 技术错误（如数据库连接失败）时
- 其他通用错误消息时

## 测试验证

### 测试用例

创建了测试脚本验证 `_remove_thinking_content` 函数的正确性：

```python
# 测试结果
原始文本长度: 997 字符
处理后文本长度: 171 字符
# 成功移除了所有 <think></think> 内容
```

### 预期效果

修改后的 API 返回示例：

```json
{
    "code": 400,
    "data": {
        "columns": [],
        "conversation_id": null,
        "rows": [],
        "session_id": null,
        "sql": null,
        "summary": null
    },
    "message": "bank_churners表中未包含客户住址字段，无法提供该信息。请尝试用其它方式提问。",
    "success": false
}
```

## 配置说明

在 `app_config.py` 中的相关配置：

```python
# 是否在摘要中显示thinking过程
# True: 显示 <think></think> 内容
# False: 隐藏 <think></think> 内容，只显示最终答案
DISPLAY_SUMMARY_THINKING = False
```

## 影响的 API 接口

1. `/api/v0/ask` - 主要的问答接口
2. `/api/v0/ask_cached` - 带缓存的问答接口

## 兼容性

- 该修改向后兼容，不会影响现有功能
- 与 `generate_summary` 方法中的 thinking 控制逻辑保持一致
- 默认配置 `DISPLAY_SUMMARY_THINKING = False` 确保用户体验的一致性

## 总结

本次修改成功实现了在 API 返回结果中控制 thinking 内容显示的功能，提升了用户体验的一致性。通过复用现有的代码逻辑，确保了功能的稳定性和可维护性。同时，添加的用户友好提示语进一步改善了用户交互体验。 