# 问题分类器关键词YAML化改造方案

## 📋 改造目标

将问题分类器中硬编码的关键词提取到独立的YAML配置文件中，实现关键词与代码的分离，提高系统的可维护性和灵活性。

## 🎯 改造背景

### 当前问题
1. **维护困难**: 关键词硬编码在`agent/classifier.py`中，修改需要改动代码
2. **业务隔离**: 业务人员无法直接维护关键词，需要开发人员参与
3. **版本管理**: 关键词变更难以独立追踪和回滚
4. **环境配置**: 不同环境难以使用不同的关键词配置

### 改造收益
1. **业务自主**: 业务人员可直接编辑YAML文件维护关键词
2. **热更新**: 支持重启生效的配置热更新
3. **版本控制**: 关键词变更可独立进行Git版本管理
4. **环境隔离**: 支持开发/测试/生产环境的差异化配置
5. **备用机制**: 保留代码备用，确保系统稳定性

## 📊 关键词类型分析

根据`agent/classifier.py`代码分析，共有**8种关键词类型**需要迁移：

| 序号 | 关键词类型 | 当前位置 | 数据结构 | 权重/作用 | 数量 |
|------|------------|----------|----------|-----------|------|
| 1 | 强业务关键词 | `classifier.py:49-79` | 字典(6个子类别) | 混合权重 | 65个 |
| 2 | 查询意图关键词 | `classifier.py:81-87` | 列表 | +1分/词 | 25个 |
| 3 | 非业务实体词 | `classifier.py:91-122` | 列表 | 立即CHAT(0.85) | ~80个 |
| 4 | SQL模式 | `classifier.py:126-129` | 正则表达式列表 | +3分/匹配 | 2个 |
| 5 | 聊天关键词 | `classifier.py:132-136` | 列表 | +1分/词 | 17个 |
| 6 | 追问关键词 | `classifier.py:139-143` | 列表 | 上下文判断 | 16个 |
| 7 | 话题切换关键词 | `classifier.py:146-150` | 列表 | 上下文判断 | 12个 |
| 8 | 业务上下文文件 | `tools/db_query_decision_prompt.txt` | 外部文本 | LLM分类辅助 | 1个文件 |

## 🏗️ 文件结构设计

### 推荐方案：独立YAML配置文件

```
agent/
├── config.py              # 现有配置文件（保持不变）
├── classifier_dict.yaml   # 新增：分类器词典配置文件
├── dict_loader.py         # 新增：词典加载器
├── classifier.py          # 修改：使用YAML配置
└── tools/
    └── db_query_decision_prompt.txt  # 保持不变
```

### 文件职责分工

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `classifier_dict.yaml` | 存储所有分类器词典配置 | 新增 |
| `dict_loader.py` | 词典加载逻辑 | 新增 |
| `config.py` | 导出词典加载函数 | 轻微修改 |
| `classifier.py` | 使用YAML配置初始化关键词 | 中等修改 |

## 📝 YAML配置文件设计

### 文件路径
```
agent/classifier_dict.yaml
```

### 文件结构设计原则
1. **层次化组织**: 保持原有的分类层次结构
2. **权重配置**: 单独配置区域，便于调优
3. **注释完整**: 每个配置项都有详细说明
4. **版本标识**: 包含配置版本信息

### 完整YAML配置文件

```yaml
# agent/classifier_dict.yaml
# 问题分类器词典配置文件
# 版本: v1.0
# 最后更新: 2024-12-XX

# ===========================================
# 配置元信息
# ===========================================
metadata:
  version: "1.0"
  description: "Citu智能数据问答平台问题分类器关键词配置"
  last_updated: "2024-12-XX"
  author: "系统管理员"

# ===========================================
# 权重配置
# ===========================================
weights:
  # 业务实体词权重（强业务关键词中除系统指示词外的部分）
  business_entity: 2
  
  # 系统指示词权重（强业务关键词中的系统查询指示词）
  system_indicator: 1
  
  # 查询意图词权重
  query_intent: 1
  
  # SQL模式权重（最高权重）
  sql_pattern: 3
  
  # 聊天关键词权重
  chat_keyword: 1
  
  # 非业务词固定置信度
  non_business_confidence: 0.85
  
  # 组合加分权重（系统指示词+业务实体词）
  combination_bonus: 3

# ===========================================
# 强业务关键词（字典结构，保持原有层次）
# ===========================================
strong_business_keywords:
  核心业务实体:
    description: "高速公路服务区基础设施和业务系统"
    keywords:
      - 服务区
      - 档口
      - 商铺
      - 收费站
      - 高速公路
      - 驿美          # 业务系统名称
      - 驿购          # 业务系统名称
      - 北区          # 物理分区
      - 南区
      - 西区
      - 东区
      - 两区
      - 停车区
      - 公司
      - 管理公司
      - 运营公司
      - 驿美运营公司
    
  支付业务:
    description: "支付方式、金额、订单等支付相关业务"
    keywords:
      # 支付方式全称
      - 微信支付
      - 支付宝支付
      - 现金支付
      - 行吧支付
      - 金豆支付
      
      # 业务指标
      - 支付金额
      - 订单数量
      - 营业额
      - 收入
      - 营业收入
      
      # 简化形式
      - 微信
      - 支付宝
      - 现金
      - 行吧
      - 金豆
      
      # 系统字段名
      - wx
      - zfb
      - rmb
      - xs
      - jd
    
  经营品类:
    description: "经营类型、品牌、商业品类"
    keywords:
      - 餐饮
      - 小吃
      - 便利店
      - 整体租赁
      - 驿美餐饮
      - 品牌
      - 经营品类
      - 商业品类
    
  车流业务:
    description: "车辆流量、车型统计等车流相关业务"
    keywords:
      # 流量概念
      - 车流量
      - 车辆数量
      - 车辆统计
      - 流量统计
      
      # 车型分类
      - 客车
      - 货车
      - 过境
      - 危化品
      - 城际
      
      # 分析概念
      - 车型分布
    
  地理路线:
    description: "高速线路、路段等地理位置信息"
    keywords:
      # 具体线路
      - 大广
      - 昌金
      - 昌栗
      
      # 概念词
      - 线路
      - 路段
      - 路线
      - 高速线路
      - 公路线路
    
  系统查询指示词:
    description: "系统、数据库等查询指示词（特殊权重处理）"
    weight: 1  # 特殊标记：权重低于其他业务实体词
    keywords:
      # 系统指示
      - 当前系统
      - 当前数据库
      - 当前数据
      - 数据库
      - 本系统
      - 系统
      
      # 数据指示
      - 数据库中
      - 数据中
      - 现有数据
      - 已有数据
      - 存储的数据
      
      # 平台指示
      - 平台数据
      - 我们的数据库
      - 这个系统

# ===========================================
# 查询意图关键词
# ===========================================
query_intent_keywords:
  description: "用于识别数据查询意图的关键词"
  keywords:
    # 统计分析
    - 统计
    - 查询
    - 分析
    - 报表
    - 报告
    - 汇总
    - 计算
    - 对比
    
    # 排序概念
    - 排行
    - 排名
    - 趋势
    - 占比
    - 百分比
    - 比例
    
    # 聚合函数
    - 最大
    - 最小
    - 最高
    - 最低
    - 平均
    - 总计
    - 合计
    - 累计
    - 求和
    - 求平均
    
    # 输出动作
    - 生成
    - 导出
    - 显示
    - 列出
    - 共有

# ===========================================
# 非业务实体词（一旦匹配立即分类为CHAT）
# ===========================================
non_business_keywords:
  description: "明确的非业务领域问题，最高优先级直接分类"
  
  农产品食物:
    - 荔枝
    - 苹果
    - 西瓜
    - 水果
    - 蔬菜
    - 大米
    - 小麦
    - 橙子
    - 香蕉
    - 葡萄
    - 草莓
    - 樱桃
    - 桃子
    - 梨
    
  技术概念:
    - 人工智能
    - 机器学习
    - 编程
    - 算法
    - 深度学习
    - AI
    - 神经网络
    - 模型训练
    - 数据挖掘
    
  身份询问:
    - 你是谁
    - 你是什么
    - 你叫什么
    - 你的名字
    - 你是什么AI
    - 什么模型
    - 大模型
    - AI助手
    - 助手
    - 机器人
    
  天气相关:
    - 天气
    - 气温
    - 下雨
    - 晴天
    - 阴天
    - 温度
    - 天气预报
    - 气候
    - 降雨
    - 雪天
    
  生活常识:
    - 怎么做饭
    - 如何减肥
    - 健康
    - 医疗
    - 病症
    - 历史
    - 地理
    - 文学
    - 电影
    - 音乐
    - 体育
    - 娱乐
    - 游戏
    - 小说
    - 新闻
    - 政治
    - 战争
    - 足球
    - NBA
    - 篮球
    - 乒乓球
    - 冠军
    - 夺冠
    - 高考
    
  旅游出行:
    - 旅游
    - 景点
    - 门票
    - 酒店
    - 机票
    - 航班
    - 高铁
    - 的士
    
  情绪表达:
    - 伤心
    - 开心
    - 无聊
    - 生气
    - 孤独
    - 累了
    - 烦恼
    - 心情
    - 难过
    - 抑郁
    
  商业金融:
    - 股票
    - 基金
    - 理财
    - 投资
    - 经济
    - 通货膨胀
    - 上市
    
  哲学思考:
    - 人生意义
    - 价值观
    - 道德
    - 信仰
    - 宗教
    - 爱情
    
  地理范围:
    - 全球
    - 全国
    - 亚洲
    - 发展中
    - 欧洲
    - 美洲
    - 东亚
    - 东南亚
    - 南美
    - 非洲
    - 大洋

# ===========================================
# SQL模式（正则表达式）
# ===========================================
sql_patterns:
  description: "用于识别SQL语句特征的正则表达式"
  patterns:
    - pattern: "\\b(select|from|where|group by|order by|having|join|update)\\b"
      description: "SQL关键字匹配"
      case_sensitive: false
      
    - pattern: "\\b(数据库|表名|表|字段名|SQL|sql|database|table)\\b"
      description: "数据库概念词匹配"
      case_sensitive: false

# ===========================================
# 聊天关键词
# ===========================================
chat_keywords:
  description: "倾向于聊天分类的关键词"
  keywords:
    # 问候语
    - 你好啊
    - 谢谢
    - 再见
    
    # 疑问词
    - 怎么样
    - 如何
    - 为什么
    - 什么是
    
    # 帮助请求
    - 介绍
    - 解释
    - 说明
    - 帮助
    - 操作
    - 使用方法
    - 功能
    - 教程
    - 指南
    - 手册
    - 讲解

# ===========================================
# 追问关键词（用于上下文判断）
# ===========================================
follow_up_keywords:
  description: "用于检测追问型问题的关键词"
  keywords:
    # 延续词
    - 还有
    - 详细
    - 具体
    - 更多
    - 继续
    - 再
    - 也
    
    # 连接词
    - 那么
    - 另外
    - 其他
    - 以及
    - 还
    - 进一步
    
    # 补充词
    - 深入
    - 补充
    - 额外
    - 此外
    - 同时
    - 并且

# ===========================================
# 话题切换关键词（用于上下文判断）
# ===========================================
topic_switch_keywords:
  description: "用于检测明显话题转换的关键词"
  keywords:
    # 问候开场
    - 你好
    - 你是
    - 谢谢
    - 再见
    
    # 功能询问
    - 介绍
    - 功能
    - 帮助
    - 使用方法
    
    # 系统询问
    - 平台
    - 系统
    - AI
    - 助手

# ===========================================
# 配置验证规则
# ===========================================
validation:
  required_sections:
    - strong_business_keywords
    - query_intent_keywords
    - non_business_keywords
    - sql_patterns
    - chat_keywords
    - follow_up_keywords
    - topic_switch_keywords
  
  min_keywords_count:
    strong_business_keywords: 50
    query_intent_keywords: 20
    non_business_keywords: 70
    chat_keywords: 15
```

## 🔧 技术实现方案

### 1. 关键词加载器设计

创建 `agent/dict_loader.py`：

```python
# agent/dict_loader.py
"""
分类器词典配置加载器
负责从YAML文件加载分类器词典配置，并提供数据转换和验证功能
"""

import yaml
import os
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from core.logging import get_agent_logger

# 初始化日志
logger = get_agent_logger("KeywordsLoader")

@dataclass
class ClassifierDictConfig:
    """分类器词典配置数据类"""
    strong_business_keywords: Dict[str, List[str]]
    query_intent_keywords: List[str]
    non_business_keywords: List[str]
    sql_patterns: List[str]
    chat_keywords: List[str]
    follow_up_keywords: List[str]
    topic_switch_keywords: List[str]
    weights: Dict[str, float]
    metadata: Dict[str, Any]

class DictLoader:
    """分类器词典配置加载器"""
    
    def __init__(self, dict_file: str = None):
        """
        初始化加载器
        
        Args:
            dict_file: 词典配置文件路径，默认为agent/classifier_dict.yaml
        """
        if dict_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dict_file = os.path.join(current_dir, "classifier_dict.yaml")
        
        self.dict_file = dict_file
        self.config_cache = None
    
    def load_config(self, force_reload: bool = False) -> ClassifierDictConfig:
        """
        加载词典配置
        
        Args:
            force_reload: 是否强制重新加载，默认使用缓存
            
        Returns:
            ClassifierDictConfig: 词典配置对象
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if self.config_cache is not None and not force_reload:
            return self.config_cache
        
        try:
            logger.info(f"加载词典配置文件: {self.dict_file}")
            
            with open(self.dict_file, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
            
            # 验证配置文件
            self._validate_config(yaml_data)
            
            # 转换数据格式
            config = self._convert_config(yaml_data)
            
            # 缓存配置
            self.config_cache = config
            
            logger.info("词典配置加载成功")
            return config
            
        except FileNotFoundError:
            error_msg = f"词典配置文件不存在: {self.dict_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        except yaml.YAMLError as e:
            error_msg = f"词典配置文件YAML格式错误: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"词典配置加载失败: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _validate_config(self, yaml_data: Dict[str, Any]) -> None:
        """验证配置文件格式和必要字段"""
        required_sections = [
            'strong_business_keywords',
            'query_intent_keywords', 
            'non_business_keywords',
            'sql_patterns',
            'chat_keywords',
            'follow_up_keywords',
            'topic_switch_keywords',
            'weights'
        ]
        
        for section in required_sections:
            if section not in yaml_data:
                raise ValueError(f"配置文件缺少必要部分: {section}")
        
        # 验证权重配置
        required_weights = [
            'business_entity',
            'system_indicator', 
            'query_intent',
            'sql_pattern',
            'chat_keyword',
            'non_business_confidence'
        ]
        
        for weight in required_weights:
            if weight not in yaml_data['weights']:
                raise ValueError(f"权重配置缺少: {weight}")
        
        logger.debug("配置文件验证通过")
    
    def _convert_config(self, yaml_data: Dict[str, Any]) -> ClassifierDictConfig:
        """将YAML数据转换为ClassifierDictConfig对象"""
        
        # 转换强业务关键词（保持字典结构）
        strong_business_keywords = {}
        for category, data in yaml_data['strong_business_keywords'].items():
            if isinstance(data, dict) and 'keywords' in data:
                strong_business_keywords[category] = data['keywords']
            else:
                # 兼容简单格式
                strong_business_keywords[category] = data
        
        # 转换查询意图关键词
        query_intent_data = yaml_data['query_intent_keywords']
        if isinstance(query_intent_data, dict) and 'keywords' in query_intent_data:
            query_intent_keywords = query_intent_data['keywords']
        else:
            query_intent_keywords = query_intent_data
        
        # 转换非业务实体词（展平为列表）
        non_business_keywords = self._flatten_non_business_keywords(
            yaml_data['non_business_keywords']
        )
        
        # 转换SQL模式
        sql_patterns = []
        patterns_data = yaml_data['sql_patterns']
        if isinstance(patterns_data, dict) and 'patterns' in patterns_data:
            for pattern_info in patterns_data['patterns']:
                if isinstance(pattern_info, dict):
                    sql_patterns.append(pattern_info['pattern'])
                else:
                    sql_patterns.append(pattern_info)
        else:
            sql_patterns = patterns_data
        
        # 转换其他关键词列表
        chat_keywords = self._extract_keywords_list(yaml_data['chat_keywords'])
        follow_up_keywords = self._extract_keywords_list(yaml_data['follow_up_keywords'])
        topic_switch_keywords = self._extract_keywords_list(yaml_data['topic_switch_keywords'])
        
        return ClassifierDictConfig(
            strong_business_keywords=strong_business_keywords,
            query_intent_keywords=query_intent_keywords,
            non_business_keywords=non_business_keywords,
            sql_patterns=sql_patterns,
            chat_keywords=chat_keywords,
            follow_up_keywords=follow_up_keywords,
            topic_switch_keywords=topic_switch_keywords,
            weights=yaml_data['weights'],
            metadata=yaml_data.get('metadata', {})
        )
    
    def _flatten_non_business_keywords(self, non_business_data: Dict[str, Any]) -> List[str]:
        """将分类的非业务词展平为列表"""
        flattened = []
        
        # 跳过description字段
        for category, keywords in non_business_data.items():
            if category == 'description':
                continue
            if isinstance(keywords, list):
                flattened.extend(keywords)
        
        return flattened
    
    def _extract_keywords_list(self, data: Any) -> List[str]:
        """从可能包含description的数据中提取关键词列表"""
        if isinstance(data, dict) and 'keywords' in data:
            return data['keywords']
        elif isinstance(data, list):
            return data
        else:
            return []

# 全局加载器实例
_dict_loader = None

def get_dict_loader() -> DictLoader:
    """获取全局词典加载器实例"""
    global _dict_loader
    if _dict_loader is None:
        _dict_loader = DictLoader()
    return _dict_loader

def load_classifier_dict_config(force_reload: bool = False) -> ClassifierDictConfig:
    """
    加载分类器词典配置（便捷函数）
    
    Args:
        force_reload: 是否强制重新加载
        
    Returns:
        ClassifierDictConfig: 词典配置对象
    """
    loader = get_dict_loader()
    return loader.load_config(force_reload)
```

### 2. config.py 修改方案

在 `agent/config.py` 中添加关键词加载函数：

```python
# 在 agent/config.py 文件末尾添加

# ==================== 关键词配置加载 ====================

try:
    from .dict_loader import load_classifier_dict_config, get_dict_loader
    
    def get_classifier_dict_config(force_reload: bool = False):
        """
        获取分类器词典配置
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            ClassifierDictConfig: 词典配置对象
        """
        return load_classifier_dict_config(force_reload)
    
    def reload_classifier_dict_config():
        """重新加载分类器词典配置"""
        return load_classifier_dict_config(force_reload=True)
    
    # 导出词典配置函数
    __all__ = [
        'get_current_config', 
        'get_nested_config', 
        'AGENT_CONFIG',
        'get_classifier_dict_config',
        'reload_classifier_dict_config'
    ]
    
except ImportError as e:
    # 如果dict_loader模块不存在，提供空实现
    def get_classifier_dict_config(force_reload: bool = False):
        raise ImportError("词典加载器模块不可用，请检查dict_loader.py是否存在")
    
    def reload_classifier_dict_config():
        raise ImportError("词典加载器模块不可用，请检查dict_loader.py是否存在")
```

### 3. classifier.py 修改方案

修改 `QuestionClassifier.__init__` 方法：

```python
# 在 QuestionClassifier.__init__ 方法中的修改

def __init__(self):
    # 初始化日志
    self.logger = get_agent_logger("Classifier")
    
    # 加载配置参数（保持现有逻辑）
    try:
        from agent.config import get_current_config, get_nested_config
        config = get_current_config()
        self.high_confidence_threshold = get_nested_config(config, "classification.high_confidence_threshold", 0.7)
        # ... 其他配置参数加载保持不变
        self.logger.info("从配置文件加载分类器参数完成")
    except ImportError:
        # ... 现有的默认配置逻辑保持不变
        self.logger.warning("配置文件不可用，使用默认分类器参数")
    
    # 加载词典配置（新增逻辑）
    self._load_dict_config()

def _load_dict_config(self):
    """加载分类器词典配置"""
    try:
        from agent.config import get_classifier_dict_config
        dict_config = get_classifier_dict_config()
        
        # 加载强业务关键词
        self.strong_business_keywords = dict_config.strong_business_keywords
        
        # 加载其他关键词列表
        self.query_intent_keywords = dict_config.query_intent_keywords
        self.non_business_keywords = dict_config.non_business_keywords
        self.chat_keywords = dict_config.chat_keywords
        self.follow_up_keywords = dict_config.follow_up_keywords
        self.topic_switch_keywords = dict_config.topic_switch_keywords
        
        # 加载SQL模式
        self.sql_patterns = dict_config.sql_patterns
        
        # 记录加载的关键词数量
        total_keywords = (
            sum(len(keywords) for keywords in self.strong_business_keywords.values()) +
            len(self.query_intent_keywords) +
            len(self.non_business_keywords) +
            len(self.chat_keywords) +
            len(self.follow_up_keywords) +
            len(self.topic_switch_keywords)
        )
        
        self.logger.info(f"从YAML配置文件加载词典完成，共加载 {total_keywords} 个关键词")
        
    except Exception as e:
        self.logger.warning(f"加载YAML词典配置失败: {str(e)}，使用代码中的备用配置")
        self._load_default_dict()

def _load_default_dict(self):
    """加载代码中的备用词典配置"""
    self.logger.info("使用代码中的默认词典配置作为备用")
    
    # 保留原有的硬编码关键词作为备用
    self.strong_business_keywords = {
        "核心业务实体": [
            "服务区", "档口", "商铺", "收费站", "高速公路",
            "驿美", "驿购",
            "北区", "南区", "西区", "东区", "两区",
            "停车区", "公司", "管理公司", "运营公司", "驿美运营公司"
        ],
        # ... 其他关键词类别的备用配置
    }
    
    # ... 其他关键词的备用配置
    
    self.logger.info("默认词典配置加载完成")
```

## 🧪 测试验证方案

### 1. 单元测试设计

创建 `test/test_dict_loader.py`：

```python
# test/test_dict_loader.py
import unittest
import tempfile
import os
import yaml
from agent.dict_loader import DictLoader, ClassifierDictConfig

class TestDictLoader(unittest.TestCase):
    """词典加载器测试"""
    
    def setUp(self):
        """测试前准备"""
        self.test_yaml_content = {
            'metadata': {'version': '1.0'},
            'weights': {
                'business_entity': 2,
                'system_indicator': 1,
                'query_intent': 1,
                'sql_pattern': 3,
                'chat_keyword': 1,
                'non_business_confidence': 0.85
            },
            'strong_business_keywords': {
                '核心业务实体': {
                    'keywords': ['服务区', '档口']
                }
            },
            'query_intent_keywords': {
                'keywords': ['统计', '查询']
            },
            'non_business_keywords': {
                '农产品食物': ['苹果', '香蕉']
            },
            'sql_patterns': {
                'patterns': [
                    {'pattern': '\\bselect\\b', 'description': 'SQL关键字'}
                ]
            },
            'chat_keywords': {
                'keywords': ['你好', '谢谢']
            },
            'follow_up_keywords': {
                'keywords': ['还有', '详细']
            },
            'topic_switch_keywords': {
                'keywords': ['你好', '你是']
            }
        }
    
    def test_load_valid_config(self):
        """测试加载有效配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.test_yaml_content, f)
            temp_file = f.name
        
        try:
            loader = DictLoader(temp_file)
            config = loader.load_config()
            
            self.assertIsInstance(config, ClassifierDictConfig)
            self.assertEqual(config.weights['business_entity'], 2)
            self.assertIn('服务区', config.strong_business_keywords['核心业务实体'])
            self.assertIn('苹果', config.non_business_keywords)
            
        finally:
            os.unlink(temp_file)
    
    def test_load_missing_file(self):
        """测试加载不存在的文件"""
        loader = DictLoader('nonexistent.yaml')
        with self.assertRaises(FileNotFoundError):
            loader.load_config()
    
    def test_load_invalid_yaml(self):
        """测试加载无效YAML"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_file = f.name
        
        try:
            loader = DictLoader(temp_file)
            with self.assertRaises(ValueError):
                loader.load_config()
        finally:
            os.unlink(temp_file)

if __name__ == '__main__':
    unittest.main()
```

### 2. 集成测试设计

创建 `test/test_classifier_yaml_integration.py`：

```python
# test/test_classifier_yaml_integration.py
import unittest
from agent.classifier import QuestionClassifier

class TestClassifierYamlIntegration(unittest.TestCase):
    """分类器YAML集成测试"""
    
    def setUp(self):
        """测试前准备"""
        self.classifier = QuestionClassifier()
    
    def test_yaml_dict_loaded(self):
        """测试YAML词典是否正确加载"""
        # 验证强业务关键词
        self.assertIsInstance(self.classifier.strong_business_keywords, dict)
        self.assertIn('核心业务实体', self.classifier.strong_business_keywords)
        
        # 验证其他关键词列表
        self.assertIsInstance(self.classifier.query_intent_keywords, list)
        self.assertIsInstance(self.classifier.non_business_keywords, list)
        self.assertIsInstance(self.classifier.chat_keywords, list)
    
    def test_classification_still_works(self):
        """测试分类功能仍然正常工作"""
        # 测试业务查询
        result = self.classifier.classify("统计服务区的微信支付金额")
        self.assertEqual(result.question_type, "DATABASE")
        
        # 测试非业务查询
        result = self.classifier.classify("苹果什么时候成熟")
        self.assertEqual(result.question_type, "CHAT")
        
        # 测试聊天查询
        result = self.classifier.classify("你好，请问如何使用")
        self.assertEqual(result.question_type, "CHAT")

if __name__ == '__main__':
    unittest.main()
```

## 📋 实施步骤

### 阶段一：基础设施搭建（1-2天）
1. ✅ 创建 `agent/classifier_dict.yaml` 配置文件
2. ✅ 创建 `agent/dict_loader.py` 加载器
3. ✅ 修改 `agent/config.py` 添加加载函数
4. ✅ 编写单元测试

### 阶段二：代码改造（1天）
1. ✅ 修改 `QuestionClassifier.__init__` 方法
2. ✅ 添加备用关键词加载逻辑
3. ✅ 编写集成测试

### 阶段三：测试验证（1天）
1. ✅ 运行单元测试和集成测试
2. ✅ 验证分类功能正确性
3. ✅ 测试异常情况处理

### 阶段四：部署上线（0.5天）
1. ✅ 部署配置文件到生产环境
2. ✅ 验证系统运行正常
3. ✅ 监控分类效果

## 🎯 预期效果

### 立即收益
1. **词典维护便利化**: 业务人员可直接编辑YAML文件
2. **配置版本化管理**: 词典变更可进行Git版本控制
3. **系统稳定性保障**: 备用机制确保配置失败时系统正常运行

### 长期收益
1. **快速业务适配**: 新业务场景的词典快速添加
2. **A/B测试支持**: 不同环境使用不同词典配置
3. **数据驱动优化**: 基于分类效果数据调整词典权重

## ⚠️ 风险控制

### 潜在风险
1. **配置文件错误**: YAML格式错误导致系统启动失败
2. **词典缺失**: 关键词遗漏影响分类准确性
3. **权重配置错误**: 权重设置不当影响分类效果

### 风险控制措施
1. **格式验证**: 加载器进行严格的YAML格式和必要字段验证
2. **备用机制**: 保留代码中的默认词典作为备用
3. **渐进式部署**: 先在测试环境验证，再逐步推广到生产环境
4. **监控告警**: 添加词典加载失败的监控和告警
5. **文档说明**: 提供详细的配置文件编辑指南

## 📈 后续优化方向

1. **热更新机制**: 实现运行时重载词典配置，无需重启
2. **可视化管理**: 开发Web界面管理词典配置
3. **智能推荐**: 基于用户查询日志推荐新关键词
4. **效果分析**: 统计各关键词的命中率和分类准确性
5. **多环境支持**: 支持开发/测试/生产环境的差异化配置

---

*本方案基于当前系统架构设计，遵循最小变更原则，确保改造过程中系统稳定运行。* 