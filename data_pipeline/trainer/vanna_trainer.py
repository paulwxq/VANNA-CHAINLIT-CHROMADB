# vanna_trainer.py
import os
import time
import threading
import queue
import concurrent.futures
from functools import lru_cache
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional, Union, Callable
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import app_config

# 设置正确的项目根目录路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 创建vanna实例
from core.vanna_llm_factory import create_vanna_instance

vn = create_vanna_instance()

# 使用新的配置工具函数获取embedding配置
try:
    from common.utils import get_current_embedding_config, get_current_model_info
    
    embedding_config = get_current_embedding_config()
    model_info = get_current_model_info()
    
    print(f"\n===== Embedding模型信息 =====")
    print(f"模型类型: {model_info['embedding_type']}")
    print(f"模型名称: {model_info['embedding_model']}")
    print(f"向量维度: {embedding_config.get('embedding_dimension', '未知')}")
    if 'base_url' in embedding_config:
        print(f"API服务: {embedding_config['base_url']}")
    print("==============================")
except ImportError as e:
    print(f"警告: 无法导入配置工具函数: {e}")
    print("使用默认配置...")
    embedding_config = getattr(app_config, 'API_EMBEDDING_CONFIG', {})
    print(f"\n===== Embedding模型信息 (默认) =====")
    print(f"模型名称: {embedding_config.get('model_name', '未知')}")
    print("==============================")

# 从app_config获取训练批处理配置
BATCH_PROCESSING_ENABLED = app_config.TRAINING_BATCH_PROCESSING_ENABLED
BATCH_SIZE = app_config.TRAINING_BATCH_SIZE
MAX_WORKERS = app_config.TRAINING_MAX_WORKERS


# 训练数据批处理器
# 专门用于优化训练过程的批处理器，将多个训练项目打包处理以提高效率
class BatchProcessor:
    def __init__(self, batch_size=BATCH_SIZE, max_workers=MAX_WORKERS):
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.batches = defaultdict(list)
        self.lock = threading.Lock()  # 线程安全锁
        
        # 初始化工作线程池
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        
        # 是否启用批处理
        self.batch_enabled = BATCH_PROCESSING_ENABLED       

        print(f"[DEBUG] 训练批处理器初始化: 启用={self.batch_enabled}, 批大小={self.batch_size}, 最大工作线程={self.max_workers}")
    
    def add_item(self, batch_type: str, item: Dict[str, Any]):
        """添加一个项目到批处理队列"""
        if not self.batch_enabled:
            # 如果未启用批处理，直接处理
            self._process_single_item(batch_type, item)
            return
        
        with self.lock:
            self.batches[batch_type].append(item)
            
            if len(self.batches[batch_type]) >= self.batch_size:
                batch_items = self.batches[batch_type]
                self.batches[batch_type] = []
                # 提交批处理任务到线程池
                self.executor.submit(self._process_batch, batch_type, batch_items)
    
    def _process_single_item(self, batch_type: str, item: Dict[str, Any]):
        """处理单个项目"""
        try:
            if batch_type == 'ddl':
                vn.train(ddl=item['ddl'])
            elif batch_type == 'documentation':
                vn.train(documentation=item['documentation'])
            elif batch_type == 'question_sql':
                vn.train(question=item['question'], sql=item['sql'])
            
            print(f"[DEBUG] 单项处理成功: {batch_type}")
                
        except Exception as e:
            print(f"[ERROR] 处理 {batch_type} 项目失败: {e}")
    
    def _process_batch(self, batch_type: str, items: List[Dict[str, Any]]):
        """处理一批项目"""
        print(f"[INFO] 开始批量处理 {len(items)} 个 {batch_type} 项")
        start_time = time.time()
        
        try:
            # 准备批处理数据
            batch_data = []
            
            if batch_type == 'ddl':
                for item in items:
                    batch_data.append({
                        'type': 'ddl',
                        'content': item['ddl']
                    })
            
            elif batch_type == 'documentation':
                for item in items:
                    batch_data.append({
                        'type': 'documentation',
                        'content': item['documentation']
                    })
            
            elif batch_type == 'question_sql':
                for item in items:
                    batch_data.append({
                        'type': 'question_sql',
                        'question': item['question'],
                        'sql': item['sql']
                    })
            
            # 使用批量添加方法
            if hasattr(vn, 'add_batch') and callable(getattr(vn, 'add_batch')):
                success = vn.add_batch(batch_data)
                if success:
                    print(f"[INFO] 批量处理成功: {len(items)} 个 {batch_type} 项")
                else:
                    print(f"[WARNING] 批量处理部分失败: {batch_type}")
            else:
                # 如果没有批处理方法，退回到逐条处理
                print(f"[WARNING] 批处理不可用，使用逐条处理: {batch_type}")
                for item in items:
                    self._process_single_item(batch_type, item)
                
        except Exception as e:
            print(f"[ERROR] 批处理 {batch_type} 失败: {e}")
            # 如果批处理失败，尝试逐条处理
            print(f"[INFO] 尝试逐条处理...")
            for item in items:
                try:
                    self._process_single_item(batch_type, item)
                except Exception as item_e:
                    print(f"[ERROR] 处理项目失败: {item_e}")
        
        elapsed = time.time() - start_time
        print(f"[INFO] 批处理完成 {len(items)} 个 {batch_type} 项，耗时 {elapsed:.2f} 秒")
    
    def flush_all(self):
        """强制处理所有剩余项目"""
        with self.lock:
            for batch_type, items in self.batches.items():
                if items:
                    print(f"[INFO] 正在处理剩余的 {len(items)} 个 {batch_type} 项")
                    self._process_batch(batch_type, items)
            
            # 清空队列
            self.batches = defaultdict(list)
        
        print("[INFO] 所有训练批处理项目已完成")
    
    def shutdown(self):
        """关闭处理器和线程池"""
        self.flush_all()
        self.executor.shutdown(wait=True)
        print("[INFO] 训练批处理器已关闭")

# 创建全局训练批处理器实例
# 用于所有训练函数的批处理优化
batch_processor = BatchProcessor()

# 原始训练函数的批处理增强版本
def train_ddl(ddl_sql: str):
    print(f"[DDL] Training on DDL:\n{ddl_sql}")
    batch_processor.add_item('ddl', {'ddl': ddl_sql})

def train_documentation(doc: str):
    print(f"[DOC] Training on documentation:\n{doc}")
    batch_processor.add_item('documentation', {'documentation': doc})

def train_sql_example(sql: str):
    """训练单个SQL示例，通过SQL生成相应的问题"""
    print(f"[SQL] Training on SQL:\n{sql}")
    
    try:
        # 直接调用generate_question方法
        question = vn.generate_question(sql=sql)
        
        question = question.strip()
        if not question.endswith("?") and not question.endswith("？"):
            question += "?"
            
    except Exception as e:
        print(f"[ERROR] 生成问题时出错: {e}")
        raise Exception(f"无法为SQL生成问题: {e}")
        
    print(f"[SQL] 生成问题: {question}")
    # 使用标准方式存储问题-SQL对
    batch_processor.add_item('question_sql', {'question': question, 'sql': sql})

def train_question_sql_pair(question: str, sql: str):
    print(f"[Q-S] Training on:\nquestion: {question}\nsql: {sql}")
    batch_processor.add_item('question_sql', {'question': question, 'sql': sql})

# 完成训练后刷新所有待处理项
def flush_training():
    """强制处理所有待处理的训练项目"""
    batch_processor.flush_all()

# 关闭训练器
def shutdown_trainer():
    """关闭训练器和相关资源"""
    batch_processor.shutdown() 