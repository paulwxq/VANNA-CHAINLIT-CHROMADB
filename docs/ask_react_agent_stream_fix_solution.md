# React Agent 流式 API 修复方案

## 问题背景

`ask_react_agent_stream` API 在使用 LangGraph 的原生 `astream` 方法时，出现了 "Event loop is closed" 错误。这是因为：

1. LangGraph 的 Redis checkpointer 使用异步连接
2. Vanna 的向量搜索是同步操作
3. Flask 的 WSGI 模型与 asyncio 事件循环管理存在冲突

用户创建了临时的 `ask_react_agent_stream_sync` API 作为变通方案，但这个方案使用的是同步 `invoke` 方法，并不是真正的流式输出。

## 核心需求

1. 修复 `ask_react_agent_stream`，使其能够使用 LangGraph 的原生 `astream` 方法
2. 保留 checkpoint 功能（对话历史记录等）
3. 不影响其他 API（特别是 `ask_react_agent`）
4. 删除临时的 `ask_react_agent_stream_sync` API

## 解决方案

### 1. 创建异步 SQL 工具

创建 `react_agent/async_sql_tools.py`，将同步的 Vanna 操作包装成异步函数：

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool
from common.vanna_instance import get_vanna_instance
from common.utils import log_to_db
from core.logging import get_logger

logger = get_logger(__name__)

# 创建线程池执行器
executor = ThreadPoolExecutor(max_workers=3)

@tool
async def generate_sql(question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """异步生成SQL查询语句"""
    def _sync_generate():
        vn = get_vanna_instance()
        
        # 构造完整的提问内容
        if history and len(history) > 0:
            context_parts = ["根据以下对话历史："]
            for h in history:
                if h.get("role") == "assistant" and h.get("content"):
                    context_parts.append(f"- {h['content']}")
            context_parts.append(f"\n当前问题：{question}")
            full_question = "\n".join(context_parts)
        else:
            full_question = question
            
        logger.info(f"📝 [Vanna Input] Complete question being sent to Vanna:")
        logger.info(f"--- BEGIN VANNA INPUT ---")
        logger.info(full_question)
        logger.info(f"--- END VANNA INPUT ---")
        
        sql = vn.generate_sql(full_question, allow_llm_to_see_data=False)
        
        if sql:
            logger.info(f"   ✅ SQL Generated Successfully:")
            logger.info(f"   {sql}")
            return sql
        else:
            logger.warning(f"   ⚠️ No SQL generated")
            return "SQL生成失败，请检查问题描述是否准确。"
    
    # 在线程池中执行同步操作
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_generate)

@tool
async def valid_sql(sql: str, question: str) -> str:
    """异步验证SQL语句的语法正确性"""
    def _sync_validate():
        # ... 同步验证逻辑 ...
        return validation_result
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_validate)

@tool
async def run_sql(sql: str, question: str) -> str:
    """异步执行SQL查询并返回结果"""
    def _sync_run():
        # ... 同步执行逻辑 ...
        return json.dumps(results_dict, ensure_ascii=False)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_run)

# 导出异步工具列表
async_sql_tools = [generate_sql, valid_sql, run_sql]
```

### 2. 修改 unified_api.py

#### 2.1 为流式 API 创建独立的 Agent 实例

每个流式请求创建新的 Agent 实例，避免事件循环冲突：

```python
async def create_stream_agent_instance():
    """为每个流式请求创建新的Agent实例（使用异步工具）"""
    if CustomReactAgent is None:
        logger.error("❌ CustomReactAgent 未能导入，无法初始化流式Agent")
        raise ImportError("CustomReactAgent 未能导入")
        
    logger.info("🚀 正在为流式请求创建新的 React Agent 实例...")
    try:
        # 创建流式专用 Agent 实例
        stream_agent = await CustomReactAgent.create()
        
        # 配置使用异步 SQL 工具
        from react_agent.async_sql_tools import async_sql_tools
        stream_agent.tools = async_sql_tools
        stream_agent.llm_with_tools = stream_agent.llm.bind_tools(async_sql_tools)
        
        logger.info("✅ 流式 React Agent 实例创建完成（配置异步工具）")
        return stream_agent
        
    except Exception as e:
        logger.error(f"❌ 流式 React Agent 实例创建失败: {e}")
        raise
```

#### 2.2 修改 ask_react_agent_stream 函数

在 Flask 路由的 generate 函数中管理事件循环：

```python
@app.route('/api/v0/ask_react_agent_stream', methods=['GET'])
def ask_react_agent_stream():
    """React Agent 流式API - 使用异步工具的专用 Agent 实例"""
    def generate():
        try:
            # ... 参数验证 ...
            
            # 3. 为当前请求创建新的事件循环和Agent实例
            import asyncio
            
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            stream_agent = None
            try:
                # 为当前请求创建新的Agent实例
                stream_agent = loop.run_until_complete(create_stream_agent_instance())
                
                if not stream_agent:
                    yield format_sse_error("流式 React Agent 初始化失败")
                    return
            except Exception as e:
                logger.error(f"流式 Agent 初始化异常: {str(e)}")
                yield format_sse_error(f"流式 Agent 初始化失败: {str(e)}")
                return
            
            # 4. 在同一个事件循环中执行流式处理
            try:
                # 创建异步生成器
                async def stream_worker():
                    try:
                        # 使用当前请求的 Agent 实例（已配置异步工具）
                        async for chunk in stream_agent.chat_stream(
                            message=validated_data['question'],
                            user_id=validated_data['user_id'],
                            thread_id=validated_data['thread_id']
                        ):
                            yield chunk
                            if chunk.get("type") == "completed":
                                break
                    except Exception as e:
                        logger.error(f"流式处理异常: {str(e)}", exc_info=True)
                        yield {
                            "type": "error", 
                            "error": f"流式处理异常: {str(e)}"
                        }
                
                # 在当前事件循环中运行异步生成器
                async_gen = stream_worker()
                
                # 同步迭代异步生成器
                while True:
                    try:
                        chunk = loop.run_until_complete(async_gen.__anext__())
                        
                        if chunk["type"] == "progress":
                            yield format_sse_react_progress(chunk)
                        elif chunk["type"] == "completed":
                            yield format_sse_react_completed(chunk)
                            break
                        elif chunk["type"] == "error":
                            yield format_sse_error(chunk.get("error", "未知错误"))
                            break
                            
                    except StopAsyncIteration:
                        break
                    except Exception as e:
                        logger.error(f"处理流式数据异常: {str(e)}")
                        yield format_sse_error(f"处理异常: {str(e)}")
                        break
                        
            except Exception as e:
                logger.error(f"React Agent流式处理异常: {str(e)}")
                yield format_sse_error(f"流式处理异常: {str(e)}")
            finally:
                # 清理：流式处理完成后关闭事件循环
                try:
                    loop.close()
                except Exception as e:
                    logger.warning(f"关闭事件循环时出错: {e}")
                    
        except Exception as e:
            logger.error(f"React Agent流式API异常: {str(e)}")
            yield format_sse_error(f"服务异常: {str(e)}")
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

## 关键改进点

1. **每个请求独立的 Agent 实例**：避免跨请求的事件循环冲突
2. **异步工具包装**：使用 ThreadPoolExecutor 将同步的 Vanna 操作转换为异步
3. **事件循环管理**：在同一个事件循环中创建和使用 Agent 实例
4. **保留 checkpoint 功能**：每个 Agent 实例都有完整的 Redis checkpoint 支持

## 测试结果

修复后的测试结果显示：

- 所有流式 API 测试用例都成功执行
- 正确显示进度信息（准备消息 → AI思考中 → 准备工具 → 执行查询 → 处理结果 → 生成回答）
- 没有再出现 "Event loop is closed" 错误
- 保留了完整的 checkpoint 功能（thread_id、对话历史等）

## 后续步骤

1. ✅ 删除临时的 `ask_react_agent_stream_sync` API
2. ✅ 在生产环境中使用修复后的 `ask_react_agent_stream` API
3. 考虑性能优化：如果需要，可以实现 Agent 实例池来减少创建开销（当前先确保功能正常）