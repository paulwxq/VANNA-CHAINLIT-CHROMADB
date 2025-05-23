import chainlit as cl
from chainlit.input_widget import Select
from vanna_llm_factory import create_vanna_instance
import os

# vn.set_api_key(os.environ['VANNA_API_KEY'])
# vn.set_model('chinook')
# vn.connect_to_sqlite('https://vanna.ai/Chinook.sqlite')

vn = create_vanna_instance()

@cl.set_chat_profiles
async def chat_profile():
    return [
        cl.ChatProfile(
            name="Vanna助手",
            markdown_description="基于Vanna的智能数据库查询助手，支持自然语言转SQL查询和数据可视化",
            icon="./public/avatars/huoche.png",
            # 备用在线图标，如果本地图标不显示可以取消注释下面的行
            #icon="https://raw.githubusercontent.com/tabler/tabler-icons/master/icons/database.svg",
        ),
    ]

@cl.step(language="sql", name="Vanna")
async def gen_query(human_query: str):
    """
    安全的SQL生成函数，处理所有可能的异常
    """
    try:
        print(f"[INFO] 开始生成SQL: {human_query}")
        sql_query = vn.generate_sql(human_query)
        
        if sql_query is None:
            print(f"[WARNING] generate_sql 返回 None")
            return None
            
        if sql_query.strip() == "":
            print(f"[WARNING] generate_sql 返回空字符串")
            return None
            
        # 检查是否返回了错误信息而非SQL
        if "insufficient context" in sql_query.lower() or "无法生成" in sql_query or "sorry" in sql_query.lower():
            print(f"[WARNING] LLM返回无法生成SQL的消息: {sql_query}")
            return None
            
        print(f"[SUCCESS] SQL生成成功: {sql_query}")
        return sql_query
        
    except Exception as e:
        print(f"[ERROR] gen_query 异常: {str(e)}")
        print(f"[ERROR] 异常类型: {type(e).__name__}")
        return None

@cl.step(name="Vanna")
async def execute_query(query):
    current_step = cl.context.current_step
    try:
        if query is None or query.strip() == "":
            current_step.output = "SQL查询为空，无法执行"
            return None
            
        print(f"[INFO] 执行SQL: {query}")
        df = vn.run_sql(query)
        
        if df is None or df.empty:
            current_step.output = "查询执行成功，但没有返回数据"
            return None
            
        current_step.output = df.head().to_markdown(index=False)
        print(f"[SUCCESS] SQL执行成功，返回 {len(df)} 行数据")
        return df
        
    except Exception as e:
        error_msg = f"SQL执行失败: {str(e)}"
        print(f"[ERROR] {error_msg}")
        current_step.output = error_msg
        return None

@cl.step(name="Plot", language="python")
async def plot(human_query, sql, df):
    current_step = cl.context.current_step
    try:
        if df is None or df.empty:
            current_step.output = "无数据可用于生成图表"
            return None
            
        plotly_code = vn.generate_plotly_code(question=human_query, sql=sql, df=df)
        fig = vn.get_plotly_figure(plotly_code=plotly_code, df=df)
        current_step.output = plotly_code
        return fig
        
    except Exception as e:
        error_msg = f"图表生成失败: {str(e)}"
        print(f"[ERROR] {error_msg}")
        current_step.output = error_msg
        return None

@cl.step(name="LLM Chat")
async def llm_chat(human_query: str, context: str = None):
    """直接与LLM对话，用于非数据库相关问题或SQL生成失败的情况"""
    current_step = cl.context.current_step
    try:
        print(f"[INFO] 使用LLM直接对话: {human_query}")
        
        # 构建更智能的提示词
        if context:
            # 有上下文时（SQL生成失败）
            system_message = (
                "你是一个友好的数据库查询助手。用户刚才的问题无法生成有效的SQL查询，"
                "可能是因为相关数据不在数据库中，或者问题需要重新表述。"
                "请友好地回复用户，解释可能的原因，并建议如何重新表述问题。"
            )
            user_message = f"用户问题：{human_query}\n\n{context}"
        else:
            # 无上下文时（一般性对话）
            system_message = (
                "你是一个友好的AI助手。你主要专注于数据库查询，"
                "但也可以回答一般性问题。如果用户询问数据相关问题，"
                "请建议他们重新表述以便进行SQL查询。"
            )
            user_message = human_query
        
        # 使用我们新增的 chat_with_llm 方法
        if hasattr(vn, 'chat_with_llm'):
            response = vn.chat_with_llm(user_message)
        else:
            # 回退方案：使用 submit_prompt
            if hasattr(vn, 'submit_prompt'):
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
                response = vn.submit_prompt(messages)
            else:
                # 最终回退方案
                response = f"我理解您的问题：'{human_query}'。我主要专注于数据库查询，如果您有数据相关的问题，请尝试重新表述，我可以帮您生成SQL查询并分析数据。"
        
        current_step.output = response
        return response
        
    except Exception as e:
        error_msg = f"LLM对话失败: {str(e)}"
        print(f"[ERROR] {error_msg}")
        fallback_response = f"抱歉，我暂时无法回答您的问题：'{human_query}'。请稍后重试，或者尝试重新表述您的问题。"
        current_step.output = fallback_response
        return fallback_response

def is_database_related_query(query: str) -> bool:
    """
    判断查询是否与数据库相关（保留函数用于调试和可能的后续优化，但不在主流程中使用）
    """
    # 数据库相关关键词
    db_keywords = [
        # 中文关键词
        '查询', '数据', '表', '统计', '分析', '汇总', '计算', '查找', '显示', 
        '列出', '多少', '总计', '平均', '最大', '最小', '排序', '筛选',
        '销售', '订单', '客户', '产品', '用户', '记录', '报表',
        # 英文关键词
        'select', 'count', 'sum', 'avg', 'max', 'min', 'table', 'data',
        'query', 'database', 'records', 'show', 'list', 'find', 'search'
    ]
    
    # 非数据库关键词
    non_db_keywords = [
        '天气', '新闻', '今天', '明天', '时间', '日期', '你好', '谢谢',
        '什么是', '如何', '为什么', '帮助', '介绍', '说明',
        'weather', 'news', 'today', 'tomorrow', 'time', 'hello', 'thank',
        'what is', 'how to', 'why', 'help', 'introduce'
    ]
    
    query_lower = query.lower()
    
    # 检查是否包含非数据库关键词
    for keyword in non_db_keywords:
        if keyword in query_lower:
            return False
    
    # 检查是否包含数据库关键词
    for keyword in db_keywords:
        if keyword in query_lower:
            return True
    
    # 默认认为是数据库相关（保守策略）
    return True

@cl.step(type="run", name="Vanna")
async def chain(human_query: str):
    """
    主要的处理链 - 方案二：尝试-回退策略
    对所有查询都先尝试生成SQL，如果失败则自动fallback到LLM对话
    """
    
    try:
        # 第一步：直接尝试生成SQL（不做预判断）
        print(f"[INFO] 尝试为查询生成SQL: {human_query}")
        sql_query = await gen_query(human_query)
        
        if sql_query is None or sql_query.strip() == "":
            # SQL生成失败，自动fallback到LLM对话
            print(f"[INFO] SQL生成失败，自动fallback到LLM对话")
            
            # 构建上下文信息
            context = (
                "我尝试为您的问题生成SQL查询，但没有成功。这可能是因为：\n"
                "1. 相关数据不在当前数据库中\n"
                "2. 问题需要更具体的表述\n"
                "3. 涉及的表或字段不在我的训练数据中"
            )
            
            response = await llm_chat(human_query, context)
            await cl.Message(content=response, author="Vanna助手").send()
            return
        
        # 第二步：SQL生成成功，执行查询
        print(f"[INFO] 成功生成SQL，开始执行: {sql_query}")
        df = await execute_query(sql_query)
        
        if df is None or df.empty:
            # SQL执行失败或无结果，提供详细信息并建议
            error_context = (
                f"我为您生成了SQL查询，但执行后没有找到相关数据。\n\n"
                f"生成的SQL:\n```sql\n{sql_query}\n```\n\n"
                f"这可能是因为查询条件太严格，或者数据库中暂时没有符合条件的记录。"
            )
            
            response = await llm_chat(
                f"用户询问：{human_query}，但SQL查询没有返回数据。请给出建议。",
                error_context
            )
            
            await cl.Message(
                content=f"{error_context}\n\n{response}", 
                author="Vanna助手"
            ).send()
            return
        
        # 第三步：成功获取数据，生成图表和返回结果
        print(f"[INFO] 成功获取数据，生成图表")
        fig = await plot(human_query, sql_query, df)

        # 创建返回元素
        elements = [
            cl.Text(name="data_table", content=df.to_markdown(index=False), display="inline")
        ]
        
        if fig is not None:
            elements.append(cl.Plotly(name="chart", figure=fig, display="inline"))
        
        await cl.Message(
            content=f"查询完成！以下是关于 '{human_query}' 的分析结果：", 
            elements=elements, 
            author="Vanna助手"
        ).send()
        
    except Exception as e:
        # 最外层异常处理 - 最终fallback
        error_msg = f"处理请求时发生意外错误: {str(e)}"
        print(f"[ERROR] {error_msg}")
        print(f"[ERROR] 异常类型: {type(e).__name__}")
        
        # 使用LLM生成友好的错误回复
        try:
            final_response = await llm_chat(
                f"系统遇到技术问题，用户询问：{human_query}，请提供友好的回复和建议。"
            )
            await cl.Message(
                content=f"抱歉，系统遇到了一些技术问题。\n\n{final_response}", 
                author="Vanna助手"
            ).send()
        except:
            # 如果连LLM都失败了，使用硬编码回复
            await cl.Message(
                content=f"抱歉，系统暂时遇到技术问题，请稍后重试。如果问题持续存在，请检查网络连接或联系技术支持。", 
                author="Vanna助手"
            ).send()

@cl.on_message
async def main(message: cl.Message):
    await chain(message.content)

@cl.on_chat_start
async def on_chat_start():
    # 发送中文欢迎消息
    welcome_message = """
🎉 **欢迎使用智能数据库查询助手！**

我可以帮助您：
- 🔍 将自然语言问题转换为SQL查询
- 📊 执行数据库查询并展示结果
- 📈 生成数据可视化图表
- 💬 回答一般性问题

请直接输入您的问题，例如：
- "交易次数最多的前5位客户是谁？"
- "查看过去30天的交易趋势"
- "你好，今天天气怎么样？"

让我们开始吧！✨
    """
    
    await cl.Message(
        content=welcome_message, 
        author="Vanna助手"
    ).send()