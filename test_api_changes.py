#!/usr/bin/env python3
"""
测试Data Pipeline API的修改
验证去除db_connection必填参数后的功能
"""

import requests
import json

def test_create_task():
    """测试创建任务（不需要db_connection参数）"""
    url = "http://localhost:8084/api/v0/data_pipeline/tasks"
    
    # 新的请求格式 - 不需要db_connection
    data = {
        "table_list_file": "data_pipeline/tables.txt",
        "business_context": "高速公路服务区管理系统测试",
        "db_name": "highway_db",  # 可选参数
        "enable_sql_validation": True,
        "enable_llm_repair": True,
        "modify_original_file": True,
        "enable_training_data_load": True
    }
    
    print("测试创建任务（使用app_config配置的数据库连接）...")
    print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
        if response.status_code == 201:
            return response.json().get('data', {}).get('task_id')
        else:
            print("任务创建失败")
            return None
            
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def test_old_format():
    """测试旧格式是否还能工作（应该报错）"""
    url = "http://localhost:8084/api/v0/data_pipeline/tasks"
    
    # 旧的请求格式 - 包含db_connection
    data = {
        "db_connection": "postgresql://user:pass@host:5432/dbname",
        "table_list_file": "data_pipeline/tables.txt",
        "business_context": "测试旧格式"
    }
    
    print("\n测试旧格式（包含db_connection，应该被忽略）...")
    print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
    except Exception as e:
        print(f"请求失败: {e}")

def test_missing_params():
    """测试缺少必需参数的情况"""
    url = "http://localhost:8084/api/v0/data_pipeline/tasks"
    
    # 缺少必需参数
    data = {
        "business_context": "只有业务上下文"
    }
    
    print("\n测试缺少必需参数（应该返回400错误）...")
    print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Data Pipeline API 修改测试")
    print("=" * 60)
    
    # 测试新格式
    task_id = test_create_task()
    
    # 测试旧格式
    test_old_format()
    
    # 测试缺少参数
    test_missing_params()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    if task_id:
        print(f"成功创建的任务ID: {task_id}")
        print(f"可以通过以下命令查看任务状态:")
        print(f"curl http://localhost:8084/api/v0/data_pipeline/tasks/{task_id}")