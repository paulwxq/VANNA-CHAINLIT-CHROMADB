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
    sql_query = vn.generate_sql(human_query)
    return sql_query

@cl.step(name="Vanna")
async def execute_query(query):
    current_step = cl.context.current_step
    df = vn.run_sql(query)
    current_step.output = df.head().to_markdown(index=False)

    return df

@cl.step(name="Plot", language="python")
async def plot(human_query, sql, df):
    current_step = cl.context.current_step
    plotly_code = vn.generate_plotly_code(question=human_query, sql=sql, df=df)
    fig = vn.get_plotly_figure(plotly_code=plotly_code, df=df)

    current_step.output = plotly_code
    return fig

@cl.step(type="run", name="Vanna")
async def chain(human_query: str):
    sql_query = await gen_query(human_query)
    df = await execute_query(sql_query)    
    fig = await plot(human_query, sql_query, df)

    # 创建表格和图表元素
    elements = [
        cl.Text(name="data_table", content=df.to_markdown(index=False), display="inline"),
        cl.Plotly(name="chart", figure=fig, display="inline")
    ]
    
    await cl.Message(content=human_query, elements=elements, author="Vanna助手").send()

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

请直接输入您想了解的数据问题，例如：
- "交易次数最多的前5位客户是谁？"
- "查看过去30天的交易趋势"

让我们开始探索数据吧！✨
    """
    
    await cl.Message(
        content=welcome_message, 
        author="Vanna助手"
    ).send()