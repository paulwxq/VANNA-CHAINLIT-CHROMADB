#!/usr/bin/env python3
"""
测试ASGI设置是否正确
"""
import sys
import importlib.util

def test_asgi_dependencies():
    """测试ASGI依赖是否可用"""
    print("🧪 测试ASGI依赖...")
    
    # 测试uvicorn
    try:
        import uvicorn
        print(f"   ✅ uvicorn: {uvicorn.__version__}")
    except ImportError:
        print("   ❌ uvicorn: 未安装")
        print("      安装命令: pip install uvicorn")
        return False
    
    # 测试asgiref
    try:
        import asgiref
        print(f"   ✅ asgiref: {asgiref.__version__}")
    except ImportError:
        print("   ❌ asgiref: 未安装")
        print("      安装命令: pip install asgiref")
        return False
    
    # 测试WsgiToAsgi
    try:
        from asgiref.wsgi import WsgiToAsgi
        print("   ✅ WsgiToAsgi: 可用")
    except ImportError:
        print("   ❌ WsgiToAsgi: 不可用")
        return False
    
    return True

def test_api_import():
    """测试API模块是否可以正常导入"""
    print("\n🧪 测试API模块导入...")
    
    try:
        from api import app
        print("   ✅ Flask应用导入成功")
        return True
    except ImportError as e:
        print(f"   ❌ Flask应用导入失败: {e}")
        return False

def test_asgi_conversion():
    """测试ASGI转换是否工作"""
    print("\n🧪 测试ASGI转换...")
    
    try:
        from asgiref.wsgi import WsgiToAsgi
        from api import app
        
        asgi_app = WsgiToAsgi(app)
        print("   ✅ WSGI到ASGI转换成功")
        return True
    except Exception as e:
        print(f"   ❌ ASGI转换失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("🚀 ASGI设置测试")
    print("=" * 50)
    
    success = True
    
    # 测试依赖
    if not test_asgi_dependencies():
        success = False
    
    # 测试API导入
    if not test_api_import():
        success = False
    
    # 测试ASGI转换
    if success and not test_asgi_conversion():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ 所有测试通过！可以使用ASGI模式启动")
        print("💡 启动命令: python api.py")
    else:
        print("❌ 测试失败，请检查依赖安装")
        print("💡 安装命令: pip install uvicorn asgiref")
    print("=" * 50)

if __name__ == "__main__":
    main()