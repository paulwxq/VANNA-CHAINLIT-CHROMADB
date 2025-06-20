# agent/classifier.py
import re
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class ClassificationResult:
    question_type: str
    confidence: float
    reason: str
    method: str

class QuestionClassifier:
    """
    增强版问题分类器：基于高速公路服务区业务上下文的智能分类
    """
    
    def __init__(self):
        # 从配置文件加载阈值参数
        try:
            from agent.config import get_current_config, get_nested_config
            config = get_current_config()
            self.high_confidence_threshold = get_nested_config(config, "classification.high_confidence_threshold", 0.7)
            self.low_confidence_threshold = get_nested_config(config, "classification.low_confidence_threshold", 0.4)
            self.max_confidence = get_nested_config(config, "classification.max_confidence", 0.9)
            self.base_confidence = get_nested_config(config, "classification.base_confidence", 0.4)
            self.confidence_increment = get_nested_config(config, "classification.confidence_increment", 0.08)
            self.llm_fallback_confidence = get_nested_config(config, "classification.llm_fallback_confidence", 0.5)
            self.uncertain_confidence = get_nested_config(config, "classification.uncertain_confidence", 0.2)
            print("[CLASSIFIER] 从配置文件加载分类器参数完成")
        except ImportError:
            self.high_confidence_threshold = 0.7
            self.low_confidence_threshold = 0.4
            self.max_confidence = 0.9
            self.base_confidence = 0.4
            self.confidence_increment = 0.08
            self.llm_fallback_confidence = 0.5
            self.uncertain_confidence = 0.2
            print("[CLASSIFIER] 配置文件不可用，使用默认分类器参数")
        
        # 基于高速公路服务区业务的精准关键词
        self.strong_business_keywords = {
            "核心业务实体": [
                "服务区", "档口", "商铺", "收费站", "高速公路",
                "驿美", "驿购",  # 业务系统名称
                "北区", "南区", "西区", "东区", "两区",  # 物理分区
                "停车区"
            ],
            "支付业务": [
                "微信支付", "支付宝支付", "现金支付", "行吧支付", "金豆支付",
                "支付金额", "订单数量", "营业额", "收入", "营业收入",
                "微信", "支付宝", "现金", "行吧", "金豆",  # 简化形式
                "wx", "zfb", "rmb", "xs", "jd"  # 系统字段名
            ],
            "经营品类": [
                "餐饮", "小吃", "便利店", "整体租赁",
                "驿美餐饮", "品牌", "经营品类", "商业品类"
            ],
            "车流业务": [
                "车流量", "车辆数量", "客车", "货车", 
                "过境", "危化品", "城际", "车辆统计",
                "流量统计", "车型分布"
            ],
            "地理路线": [
                "大广", "昌金", "昌栗", "线路", "路段", "路线",
                "高速线路", "公路线路"
            ]
        }
        
        # 查询意图词（辅助判断）
        self.query_intent_keywords = [
            "统计", "查询", "分析", "排行", "排名",
            "报表", "报告", "汇总", "计算", "对比",
            "趋势", "占比", "百分比", "比例",
            "最大", "最小", "最高", "最低", "平均",
            "总计", "合计", "累计", "求和", "求平均",
            "生成", "导出", "显示", "列出"
        ]
        
        # 非业务实体词（包含则倾向CHAT）
        self.non_business_keywords = [
            # 农产品/食物
            "荔枝", "苹果", "西瓜", "水果", "蔬菜", "大米", "小麦",
            "橙子", "香蕉", "葡萄", "草莓", "樱桃", "桃子", "梨",
            
            # 技术概念  
            "人工智能", "机器学习", "编程", "算法", "深度学习",
            "AI", "神经网络", "模型训练", "数据挖掘",
            
            # 身份询问
            "你是谁", "你是什么", "你叫什么", "你的名字", 
            "什么模型", "大模型", "AI助手", "助手", "机器人",
            
            # 天气相关
            "天气", "气温", "下雨", "晴天", "阴天", "温度",
            "天气预报", "气候", "降雨", "雪天",
            
            # 其他生活常识
            "怎么做饭", "如何减肥", "健康", "医疗", "病症",
            "历史", "地理", "文学", "电影", "音乐", "体育",
            "娱乐", "游戏", "小说", "新闻", "政治"
        ]
        
        # SQL关键词（技术层面的数据库操作）
        self.sql_patterns = [
            r"\b(select|from|where|group by|order by|having|join)\b",
            r"\b(数据库|表名|字段名|SQL|sql)\b"
        ]
        
        # 聊天关键词（平台功能和帮助）
        self.chat_keywords = [
            "你好", "谢谢", "再见", "怎么样", "如何", "为什么", "什么是",
            "介绍", "解释", "说明", "帮助", "操作", "使用方法", "功能",
            "教程", "指南", "手册"
        ]
    
    def classify(self, question: str) -> ClassificationResult:
        """
        主分类方法：规则预筛选 + 增强LLM分类
        """
        # 第一步：规则预筛选
        rule_result = self._rule_based_classify(question)
        
        # 如果规则分类有高置信度，直接使用
        if rule_result.confidence >= self.high_confidence_threshold:
            return rule_result
        
        # 第二步：使用增强的LLM分类
        llm_result = self._enhanced_llm_classify(question)
        
        # 选择置信度更高的结果
        if llm_result.confidence > rule_result.confidence:
            return llm_result
        else:
            return rule_result
    
    def _rule_based_classify(self, question: str) -> ClassificationResult:
        """基于规则的预分类"""
        question_lower = question.lower()
        
        # 检查非业务实体词
        non_business_matched = []
        for keyword in self.non_business_keywords:
            if keyword in question_lower:
                non_business_matched.append(keyword)
        
        # 如果包含非业务实体词，直接分类为CHAT
        if non_business_matched:
            return ClassificationResult(
                question_type="CHAT",
                confidence=0.85,
                reason=f"包含非业务实体词: {non_business_matched}",
                method="rule_based_non_business"
            )
        
        # 检查强业务关键词
        business_score = 0
        business_matched = []
        
        for category, keywords in self.strong_business_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    business_score += 2  # 业务实体词权重更高
                    business_matched.append(f"{category}:{keyword}")
        
        # 检查查询意图词
        intent_score = 0
        intent_matched = []
        for keyword in self.query_intent_keywords:
            if keyword in question_lower:
                intent_score += 1
                intent_matched.append(keyword)
        
        # 检查SQL模式
        sql_patterns_matched = []
        for pattern in self.sql_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                business_score += 3  # SQL模式权重最高
                sql_patterns_matched.append(pattern)
        
        # 检查聊天关键词
        chat_score = 0
        chat_matched = []
        for keyword in self.chat_keywords:
            if keyword in question_lower:
                chat_score += 1
                chat_matched.append(keyword)
        
        # 分类决策逻辑
        total_business_score = business_score + intent_score
        
        # 强业务特征：包含业务实体 + 查询意图
        if business_score >= 2 and intent_score >= 1:
            confidence = min(self.max_confidence, 0.8 + (total_business_score * 0.05))
            return ClassificationResult(
                question_type="DATABASE",
                confidence=confidence,
                reason=f"强业务特征 - 业务实体: {business_matched}, 查询意图: {intent_matched}, SQL: {sql_patterns_matched}",
                method="rule_based_strong_business"
            )
        
        # 中等业务特征：包含多个业务实体词
        elif business_score >= 4:
            confidence = min(self.max_confidence, 0.7 + (business_score * 0.03))
            return ClassificationResult(
                question_type="DATABASE", 
                confidence=confidence,
                reason=f"中等业务特征 - 业务实体: {business_matched}",
                method="rule_based_medium_business"
            )
        
        # 聊天特征
        elif chat_score >= 1 and business_score == 0:
            confidence = min(self.max_confidence, self.base_confidence + (chat_score * self.confidence_increment))
            return ClassificationResult(
                question_type="CHAT",
                confidence=confidence,
                reason=f"聊天特征: {chat_matched}",
                method="rule_based_chat"
            )
        
        # 不确定情况
        else:
            return ClassificationResult(
                question_type="UNCERTAIN",
                confidence=self.uncertain_confidence,
                reason=f"规则分类不确定 - 业务分:{business_score}, 意图分:{intent_score}, 聊天分:{chat_score}",
                method="rule_based_uncertain"
            )
    
    def _enhanced_llm_classify(self, question: str) -> ClassificationResult:
        """增强的LLM分类：包含详细的业务上下文"""
        try:
            from common.vanna_instance import get_vanna_instance
            vn = get_vanna_instance()
            
            # 构建包含业务上下文的分类提示词
            classification_prompt = f"""
请判断以下用户问题是否需要查询我们的高速公路服务区管理数据库。

用户问题：{question}

=== 数据库业务范围 ===
本系统是高速公路服务区商业管理系统，包含以下业务数据：

核心业务实体：
- 服务区(bss_service_area)：服务区基础信息、位置、状态，如"鄱阳湖服务区"、"信丰西服务区"
- 档口/商铺(bss_branch)：档口信息、品类(餐饮/小吃/便利店)、品牌，如"驿美餐饮"、"加水机"
- 营业数据(bss_business_day_data)：每日支付金额、订单数量，包含微信、支付宝、现金等支付方式
- 车流量(bss_car_day_count)：按车型统计的日流量数据，包含客车、货车、过境、危化品等
- 公司信息(bss_company)：服务区管理公司，如"驿美运营公司"

关键业务指标：
- 支付方式：微信支付(wx)、支付宝支付(zfb)、现金支付(rmb)、行吧支付(xs)、金豆支付(jd)
- 营业数据：支付金额、订单数量、营业额、收入统计
- 车流统计：按车型(客车/货车/过境/危化品/城际)的流量分析
- 经营分析：餐饮、小吃、便利店、整体租赁等品类收入
- 地理分区：北区、南区、西区、东区、两区

高速线路：
- 线路信息：大广、昌金、昌栗等高速线路
- 路段管理：按线路统计服务区分布

=== 判断标准 ===
1. **DATABASE类型** - 需要查询数据库：
   - 涉及上述业务实体和指标的查询、统计、分析、报表
   - 包含业务相关的时间查询，如"本月服务区营业额"、"上月档口收入"
   - 例如："本月营业额统计"、"档口收入排行"、"车流量分析"、"支付方式占比"

2. **CHAT类型** - 不需要查询数据库：
   - 生活常识：水果蔬菜上市时间、动植物知识、天气等
   - 身份询问：你是谁、什么模型、AI助手等
   - 技术概念：人工智能、编程、算法等
   - 平台使用：功能介绍、操作帮助、使用教程等
   - 例如："荔枝几月份上市"、"今天天气如何"、"你是什么AI"、"怎么使用平台"

**重要提示：**
- 只有涉及高速公路服务区业务数据的问题才分类为DATABASE
- 即使包含时间词汇（如"月份"、"时间"），也要看是否与我们的业务数据相关
- 农产品上市时间、生活常识等都应分类为CHAT

请基于问题与我们高速公路服务区业务数据的相关性来分类。

格式：
分类: [DATABASE/CHAT]
理由: [详细说明问题与业务数据的相关性，具体分析涉及哪些业务实体或为什么不相关]
置信度: [0.0-1.0之间的数字]
"""
            
            # 专业的系统提示词
            system_prompt = """你是一个专业的业务问题分类助手，专门负责高速公路服务区管理系统的问题分类。你具有以下特长：
1. 深度理解高速公路服务区业务领域和数据范围
2. 准确区分业务数据查询需求和一般性问题  
3. 基于具体业务上下文进行精准分类，而不仅仅依赖关键词匹配
4. 对边界情况能够给出合理的置信度评估

请严格按照业务相关性进行分类，并提供详细的分类理由。"""
            
            # 使用 Vanna 实例的 chat_with_llm 方法
            response = vn.chat_with_llm(
                question=classification_prompt,
                system_prompt=system_prompt
            )
            
            # 解析响应
            return self._parse_llm_response(response)
            
        except Exception as e:
            print(f"[WARNING] 增强LLM分类失败: {str(e)}")
            return ClassificationResult(
                question_type="CHAT",  # 失败时默认为CHAT，更安全
                confidence=self.llm_fallback_confidence,
                reason=f"LLM分类异常，默认为聊天: {str(e)}",
                method="llm_error"
            )
    
    def _parse_llm_response(self, response: str) -> ClassificationResult:
        """解析LLM响应"""
        try:
            lines = response.strip().split('\n')
            
            question_type = "CHAT"  # 默认为CHAT
            reason = "LLM响应解析失败"
            confidence = self.llm_fallback_confidence
            
            for line in lines:
                line = line.strip()
                if line.startswith("分类:") or line.startswith("Classification:"):
                    type_part = line.split(":", 1)[1].strip().upper()
                    if "DATABASE" in type_part:
                        question_type = "DATABASE"
                    elif "CHAT" in type_part:
                        question_type = "CHAT"
                
                elif line.startswith("理由:") or line.startswith("Reason:"):
                    reason = line.split(":", 1)[1].strip()
                
                elif line.startswith("置信度:") or line.startswith("Confidence:"):
                    try:
                        conf_str = line.split(":", 1)[1].strip()
                        confidence = float(conf_str)
                        # 确保置信度在合理范围内
                        confidence = max(0.0, min(1.0, confidence))
                    except:
                        confidence = self.llm_fallback_confidence
            
            return ClassificationResult(
                question_type=question_type,
                confidence=confidence,
                reason=reason,
                method="enhanced_llm"
            )
            
        except Exception as e:
            return ClassificationResult(
                question_type="CHAT",  # 解析失败时默认为CHAT
                confidence=self.llm_fallback_confidence,
                reason=f"响应解析失败: {str(e)}",
                method="llm_parse_error"
            )