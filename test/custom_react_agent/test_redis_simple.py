#!/usr/bin/env python3
"""
超简单的Redis测试脚本
"""
import redis
import json

def test_redis_connection():
    """测试Redis连接"""
    print("🔗 测试Redis连接...")
    
    try:
        # 创建Redis连接
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        # 测试连接
        r.ping()
        print("✅ Redis连接成功")
        
        # 扫描所有checkpoint keys
        pattern = "checkpoint:*"
        print(f"🔍 扫描所有checkpoint keys...")
        
        keys = []
        cursor = 0
        count = 0
        
        while True:
            cursor, batch = r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            count += len(batch)
            print(f"   已扫描 {count} 个keys...")
            if cursor == 0:
                break
            if count > 1000:  # 限制扫描数量
                break
        
        print(f"📋 总共找到 {len(keys)} 个checkpoint keys")
        
        # 显示前几个key的格式
        print("🔍 Key格式示例:")
        for i, key in enumerate(keys[:5]):
            print(f"   [{i+1}] {key}")
        
        # 查找doudou用户的keys
        doudou_keys = [k for k in keys if k.startswith("checkpoint:doudou:")]
        print(f"👤 doudou用户的keys: {len(doudou_keys)} 个")
        
        if doudou_keys:
            print("📝 doudou的key示例:")
            for i, key in enumerate(doudou_keys[:3]):
                print(f"   [{i+1}] {key}")
                
                # 尝试获取数据
                data = r.get(key)
                if data:
                    try:
                        parsed = json.loads(data)
                        print(f"       数据大小: {len(data)} 字符")
                        print(f"       数据类型: {type(parsed)}")
                        if isinstance(parsed, dict):
                            print(f"       顶级keys: {list(parsed.keys())}")
                    except Exception as e:
                        print(f"       解析失败: {e}")
        
        r.close()
        return True
        
    except Exception as e:
        print(f"❌ Redis测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_redis_connection() 