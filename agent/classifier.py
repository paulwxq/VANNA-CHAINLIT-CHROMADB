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
    多策略融合的问题分类器
    策略：规则优先 + LLM fallback
    """
    
    def __init__(self):
        # 从配置文件加载阈值参数
        try:
            from agent.config import get_current_config, get_nested_config
            config = get_current_config()
            self.high_confidence_threshold = get_nested_config(config, "classification.high_confidence_threshold", 0.8)
            self.low_confidence_threshold = get_nested_config(config, "classification.low_confidence_threshold", 0.4)
            self.max_confidence = get_nested_config(config, "classification.max_confidence", 0.9)
            self.base_confidence = get_nested_config(config, "classification.base_confidence", 0.5)
            self.confidence_increment = get_nested_config(config, "classification.confidence_increment", 0.1)
            self.llm_fallback_confidence = get_nested_config(config, "classification.llm_fallback_confidence", 0.5)
            self.uncertain_confidence = get_nested_config(config, "classification.uncertain_confidence", 0.2)
            print("[CLASSIFIER] 从配置文件加载分类器参数完成")
        except ImportError:
            # 配置文件不可用时的默认值
            self.high_confidence_threshold = 0.8
            self.low_confidence_threshold = 0.4
            self.max_confidence = 0.9
            self.base_confidence = 0.5
            self.confidence_increment = 0.1
            self.llm_fallback_confidence = 0.5
            self.uncertain_confidence = 0.2
            print("[CLASSIFIER] 配置文件不可用，使用默认分类器参数")
        
        self.db_keywords = {
            "数据类": [
                "收入", "销量", "数量", "平均", "总计", "统计", "合计", "累计",
                "营业额", "利润", "成本", "费用", "金额", "价格", "单价"
            ],
            "分析类": [
                "分组", "排行", "排名", "增长率", "趋势", "对比", "比较", "占比",
                "百分比", "比例", "环比", "同比", "最大", "最小", "最高", "最低"
            ],
            "时间类": [
                "今天", "昨天", "本月", "上月", "去年", "季度", "年度", "月份",
                "本年", "上年", "本周", "上周", "近期", "最近"
            ],
            "业务类": [
                "客户", "订单", "产品", "商品", "用户", "会员", "供应商", "库存",
                "部门", "员工", "项目", "合同", "发票", "账单"
            ]
        }
        
        # SQL关键词
        self.sql_patterns = [
            r"\b(select|from|where|group by|order by|having|join)\b",
            r"\b(查询|统计|汇总|计算|分析)\b",
            r"\b(表|字段|数据库)\b"
        ]
        
        # 聊天关键词
        self.chat_keywords = [
            "你好", "谢谢", "再见", "怎么样", "如何", "为什么", "什么是",
            "介绍", "解释", "说明", "帮助", "操作", "使用方法", "功能"
        ]
    
    def classify(self, question: str) -> ClassificationResult:
        """
        主分类方法：规则优先 + LLM fallback
        """
        # 第一步：规则分类
        rule_result = self._rule_based_classify(question)
        
        if rule_result.confidence >= self.high_confidence_threshold:
            return rule_result
        
        # 第二步：LLM分类（针对不确定的情况）
        if rule_result.confidence <= self.low_confidence_threshold:
            llm_result = self._llm_classify(question)
            
            # 如果LLM也不确定，返回不确定状态
            if llm_result.confidence <= self.low_confidence_threshold:
                return ClassificationResult(
                    question_type="UNCERTAIN",
                    confidence=max(rule_result.confidence, llm_result.confidence),
                    reason=f"规则和LLM都不确定: {rule_result.reason} | {llm_result.reason}",
                    method="hybrid_uncertain"
                )
            
            return llm_result
        
        return rule_result
    
    def _rule_based_classify(self, question: str) -> ClassificationResult:
        """基于规则的分类"""
        question_lower = question.lower()
        
        # 检查数据库相关关键词
        db_score = 0
        matched_keywords = []
        
        for category, keywords in self.db_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    db_score += 1
                    matched_keywords.append(f"{category}:{keyword}")
        
        # 检查SQL模式
        sql_patterns_matched = []
        for pattern in self.sql_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                db_score += 2  # SQL模式权重更高
                sql_patterns_matched.append(pattern)
        
        # 检查聊天关键词
        chat_score = 0
        chat_keywords_matched = []
        for keyword in self.chat_keywords:
            if keyword in question_lower:
                chat_score += 1
                chat_keywords_matched.append(keyword)
        
        # 计算置信度和分类
        total_score = db_score + chat_score
        
        if db_score > chat_score and db_score >= 1:
            confidence = min(self.max_confidence, self.base_confidence + (db_score * self.confidence_increment))
            return ClassificationResult(
                question_type="DATABASE",
                confidence=confidence,
                reason=f"匹配数据库关键词: {matched_keywords}, SQL模式: {sql_patterns_matched}",
                method="rule_based"
            )
        elif chat_score > db_score and chat_score >= 1:
            confidence = min(self.max_confidence, self.base_confidence + (chat_score * self.confidence_increment))
            return ClassificationResult(
                question_type="CHAT",
                confidence=confidence,
                reason=f"匹配聊天关键词: {chat_keywords_matched}",
                method="rule_based"
            )
        else:
            # 没有明确匹配
            return ClassificationResult(
                question_type="UNCERTAIN",
                confidence=self.uncertain_confidence,
                reason="没有匹配到明确的关键词模式",
                method="rule_based"
            )
    
    def _llm_classify(self, question: str) -> ClassificationResult:
        """基于LLM的分类"""
        try:
            from common.utils import get_current_llm_config
            from customllm.qianwen_chat import QianWenChat
            
            llm_config = get_current_llm_config()
            llm = QianWenChat(config=llm_config)
            
            # 分类提示词
            classification_prompt = f"""
请判断以下问题是否需要查询数据库。

问题: {question}

判断标准:
1. 如果问题涉及数据查询、统计、分析、报表等，返回 "DATABASE"
2. 如果问题是一般性咨询、概念解释、操作指导、闲聊等，返回 "CHAT"

请只返回 "DATABASE" 或 "CHAT"，并在下一行简要说明理由。

格式:
分类: [DATABASE/CHAT]
理由: [简要说明]
置信度: [0.0-1.0之间的数字]
"""
            
            prompt = [
                llm.system_message("你是一个专业的问题分类助手，能准确判断问题类型。"),
                llm.user_message(classification_prompt)
            ]
            
            response = llm.submit_prompt(prompt)
            
            # 解析响应
            return self._parse_llm_response(response)
            
        except Exception as e:
            print(f"[WARNING] LLM分类失败: {str(e)}")
            return ClassificationResult(
                question_type="UNCERTAIN",
                confidence=self.llm_fallback_confidence,
                reason=f"LLM分类异常: {str(e)}",
                method="llm_error"
            )
    
    def _parse_llm_response(self, response: str) -> ClassificationResult:
        """解析LLM响应"""
        try:
            lines = response.strip().split('\n')
            
            question_type = "UNCERTAIN"
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
                    except:
                        confidence = self.llm_fallback_confidence
            
            return ClassificationResult(
                question_type=question_type,
                confidence=confidence,
                reason=reason,
                method="llm_based"
            )
            
        except Exception as e:
            return ClassificationResult(
                question_type="UNCERTAIN",
                confidence=self.llm_fallback_confidence,
                reason=f"响应解析失败: {str(e)}",
                method="llm_parse_error"
            )