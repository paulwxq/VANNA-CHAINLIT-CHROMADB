"""
ASGI应用启动文件
将Flask WSGI应用转换为ASGI应用，支持异步路由

启动方式：
1. 开发环境：python unified_api.py (直接Flask)
2. 生产环境：uvicorn asgi_app:asgi_app (ASGI服务器)
"""
from asgiref.wsgi import WsgiToAsgi
from unified_api import app

# 将Flask WSGI应用转换为ASGI应用
asgi_app = WsgiToAsgi(app)

# 启动方式示例：
# 开发环境（单进程 + 重载）：
# uvicorn asgi_app:asgi_app --host 127.0.0.1 --port 8084 --reload

# 生产环境（多进程 + 性能优化）：
# uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8084 --workers 4 --limit-concurrency 100 --limit-max-requests 1000 --access-log