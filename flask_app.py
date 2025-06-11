# 给dataops 对话助手返回结果
from flask import Flask, jsonify, request
from core.vanna_llm_factory import create_vanna_instance

app = Flask(__name__)
vn = create_vanna_instance()

@app.route('/ask', methods=['POST'])
def ask_endpoint():
    try:
        data = request.json
        question = data.get('question', '')
        if not question:
            return jsonify({"error": "Question is required"}), 400
        
        # 获取SQL答案
        result = vn.ask(question)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)