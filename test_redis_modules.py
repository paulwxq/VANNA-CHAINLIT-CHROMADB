#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis模块测试脚本
用于检测Redis服务器是否安装了RediSearch和ReJSON模块
"""

import redis
import sys
from typing import Dict, Any


def test_redis_modules(host: str = 'localhost', port: int = 6379, password: str = None, db: int = 0) -> Dict[str, Any]:
    """
    测试Redis服务器是否安装了RediSearch和ReJSON模块
    
    Args:
        host: Redis服务器地址
        port: Redis服务器端口
        password: Redis密码（可选）
        db: 数据库编号
    
    Returns:
        包含测试结果的字典
    """
    results = {
        'redis_connection': False,
        'redijson_available': False,
        'redisearch_available': False,
        'errors': []
    }
    
    try:
        # 连接Redis
        r = redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)
        
        # 测试连接
        r.ping()
        results['redis_connection'] = True
        print(f"✅ Redis连接成功 - {host}:{port}")
        
    except Exception as e:
        error_msg = f"❌ Redis连接失败: {str(e)}"
        results['errors'].append(error_msg)
        print(error_msg)
        return results
    
    # 测试RedisJSON
    try:
        # 尝试设置JSON文档
        r.execute_command('JSON.SET', 'test_doc', '$', '{"test":"value"}')
        # 尝试获取JSON文档
        result = r.execute_command('JSON.GET', 'test_doc')
        # 清理测试数据
        r.execute_command('JSON.DEL', 'test_doc')
        
        results['redijson_available'] = True
        print("✅ RedisJSON 模块可用")
        
    except redis.exceptions.ResponseError as e:
        error_msg = f"❌ RedisJSON 模块不可用: {str(e)}"
        results['errors'].append(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = f"❌ RedisJSON 测试失败: {str(e)}"
        results['errors'].append(error_msg)
        print(error_msg)
    
    # 测试RediSearch
    try:
        # 尝试创建索引
        r.execute_command('FT.CREATE', 'test_idx', 'ON', 'HASH', 'PREFIX', '1', 'test:', 'SCHEMA', 'title', 'TEXT')
        # 清理测试索引
        r.execute_command('FT.DROPINDEX', 'test_idx')
        
        results['redisearch_available'] = True
        print("✅ RediSearch 模块可用")
        
    except redis.exceptions.ResponseError as e:
        error_msg = f"❌ RediSearch 模块不可用: {str(e)}"
        results['errors'].append(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = f"❌ RediSearch 测试失败: {str(e)}"
        results['errors'].append(error_msg)
        print(error_msg)
    
    return results


def main():
    """主函数"""
    print("=" * 60)
    print("Redis模块测试工具")
    print("=" * 60)
    
    # 获取用户输入的Redis连接信息
    print("\n请输入Redis服务器连接信息:")
    host = 'localhost'
    port_input = '6379'
    password =  None
    db_input = '0'
    
    try:
        port = int(port_input)
        db = int(db_input)
    except ValueError:
        print("❌ 端口和数据库编号必须是数字")
        sys.exit(1)
    
    print(f"\n正在测试Redis服务器: {host}:{port}")
    print("-" * 40)
    
    # 执行测试
    results = test_redis_modules(host=host, port=port, password=password, db=db)
    
    # 输出测试总结
    print("\n" + "=" * 60)
    print("测试结果总结:")
    print("=" * 60)
    
    if results['redis_connection']:
        print("✅ Redis连接: 成功")
    else:
        print("❌ Redis连接: 失败")
    
    if results['redijson_available']:
        print("✅ RedisJSON: 已安装")
    else:
        print("❌ RedisJSON: 未安装")
    
    if results['redisearch_available']:
        print("✅ RediSearch: 已安装")
    else:
        print("❌ RediSearch: 未安装")
    
    if results['errors']:
        print(f"\n错误信息:")
        for error in results['errors']:
            print(f"  - {error}")
    
    print("\n" + "=" * 60)
    
    # 返回适当的退出码
    if results['redis_connection'] and results['redijson_available'] and results['redisearch_available']:
        print("🎉 所有模块都可用！")
        sys.exit(0)
    else:
        print("⚠️  部分模块不可用，请检查Redis配置")
        sys.exit(1)


if __name__ == "__main__":
    main() 