"""
ASGI应用启动文件
提供独立的ASGI启动选项，用于生产环境或uvicorn命令行启动
"""
from asgiref.wsgi import WsgiToAsgi
from api import app

# 将Flask WSGI应用转换为ASGI应用
asgi_app = WsgiToAsgi(app)

# 这个文件可以通过以下方式启动：
# uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8000
# 或
# uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8000 --reload