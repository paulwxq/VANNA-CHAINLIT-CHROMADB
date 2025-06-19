"""
Vanna实例单例管理器
统一管理整个应用中的 Vanna 实例，确保真正的单例模式
"""
import threading
from typing import Optional
from core.vanna_llm_factory import create_vanna_instance

# 全局变量
_vanna_instance: Optional[object] = None
_instance_lock = threading.Lock()  # 线程安全锁

def get_vanna_instance():
    """
    获取Vanna实例（懒加载单例，线程安全）
    
    Returns:
        Vanna实例
    """
    global _vanna_instance
    
    # 双重检查锁定模式，确保线程安全和性能
    if _vanna_instance is None:
        with _instance_lock:
            if _vanna_instance is None:
                print("[VANNA_SINGLETON] 创建 Vanna 实例...")
                try:
                    _vanna_instance = create_vanna_instance()
                    print("[VANNA_SINGLETON] Vanna 实例创建成功")
                except Exception as e:
                    print(f"[ERROR] Vanna 实例创建失败: {str(e)}")
                    raise
    
    return _vanna_instance

def reset_vanna_instance():
    """
    重置Vanna实例（用于测试或配置更改后的重新初始化）
    """
    global _vanna_instance
    with _instance_lock:
        if _vanna_instance is not None:
            print("[VANNA_SINGLETON] 重置 Vanna 实例")
            _vanna_instance = None

def get_instance_status() -> dict:
    """
    获取实例状态信息（用于调试和健康检查）
    
    Returns:
        包含实例状态的字典
    """
    global _vanna_instance
    return {
        "instance_created": _vanna_instance is not None,
        "instance_type": type(_vanna_instance).__name__ if _vanna_instance else None,
        "thread_safe": True
    } 