# 给dataops 对话助手返回结果
from vanna.flask import VannaFlaskApp
from vanna_llm_factory import create_vanna_instance
from flask import request, jsonify
import pandas as pd

vn = create_vanna_instance()

# 实例化 VannaFlaskApp
app = VannaFlaskApp(
    vn,
    title="辞图智能数据问答平台",
    logo = "https://www.citupro.com/img/logo-black-2.png",
    subtitle="让 AI 为你写 SQL",
    chart=True,
    allow_llm_to_see_data=True,
    ask_results_correct=True,
    followup_questions=True,
    debug=True
)


print("正在启动Flask应用...")
app.run(host="0.0.0.0", port=8084, debug=True)