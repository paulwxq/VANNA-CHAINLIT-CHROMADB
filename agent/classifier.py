# agent/classifier.py
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from core.logging import get_agent_logger

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
        # 初始化日志
        self.logger = get_agent_logger("Classifier")
        
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
            self.medium_confidence_threshold = get_nested_config(config, "classification.medium_confidence_threshold", 0.6)
            self.logger.info("从配置文件加载分类器参数完成")
        except ImportError:
            self.high_confidence_threshold = 0.7
            self.low_confidence_threshold = 0.4
            self.max_confidence = 0.9
            self.base_confidence = 0.4
            self.confidence_increment = 0.08
            self.llm_fallback_confidence = 0.5
            self.uncertain_confidence = 0.2
            self.medium_confidence_threshold = 0.6
            self.logger.warning("配置文件不可用，使用默认分类器参数")
        
        # 加载词典配置（新增逻辑）
        self._load_dict_config()

    def _load_dict_config(self):
        """加载分类器词典配置"""
        try:
            from agent.config import get_classifier_dict_config
            dict_config = get_classifier_dict_config()
            
            # 加载关键词列表
            self.strong_business_keywords = dict_config.strong_business_keywords
            self.query_intent_keywords = dict_config.query_intent_keywords
            self.non_business_keywords = dict_config.non_business_keywords
            self.sql_patterns = dict_config.sql_patterns
            self.chat_keywords = dict_config.chat_keywords
            
            # 加载权重配置
            self.weights = dict_config.weights
            
            # 加载其他配置
            self.metadata = dict_config.metadata
            
            total_keywords = (
                sum(len(keywords) for keywords in self.strong_business_keywords.values()) +
                len(self.query_intent_keywords) +
                len(self.non_business_keywords) +
                len(self.sql_patterns) +
                len(self.chat_keywords)
            )
            
            self.logger.info(f"从YAML配置文件加载词典完成，共加载 {total_keywords} 个关键词")
            
        except Exception as e:
            self.logger.warning(f"加载YAML词典配置失败: {str(e)}，使用代码中的备用配置")
            self._load_default_dict()

    def _load_default_dict(self):
        """YAML配置加载失败时的处理"""
        error_msg = "YAML词典配置文件加载失败，无法初始化分类器"
        self.logger.error(error_msg)
        
        # 初始化空的weights字典，使用代码中的默认值
        self.weights = {}
        
        raise RuntimeError(error_msg)

    def classify(self, question: str, context_type: Optional[str] = None, routing_mode: Optional[str] = None) -> ClassificationResult:
        """
        主分类方法：简化为混合分类策略
        
        Args:
            question: 当前问题
            context_type: 上下文类型（保留参数兼容性，但不使用）
            routing_mode: 路由模式，可选，用于覆盖配置文件设置
        """
        # 确定使用的路由模式
        if routing_mode:
            QUESTION_ROUTING_MODE = routing_mode
            self.logger.info(f"使用传入的路由模式: {QUESTION_ROUTING_MODE}")
        else:
            try:
                from app_config import QUESTION_ROUTING_MODE
                self.logger.info(f"使用配置文件路由模式: {QUESTION_ROUTING_MODE}")
            except ImportError:
                QUESTION_ROUTING_MODE = "hybrid"
                self.logger.info(f"配置导入失败，使用默认路由模式: {QUESTION_ROUTING_MODE}")
        
        # 根据路由模式选择分类策略
        if QUESTION_ROUTING_MODE == "database_direct":
            return ClassificationResult(
                question_type="DATABASE",
                confidence=1.0,
                reason="配置为直接数据库查询模式",
                method="direct_database"
            )
        elif QUESTION_ROUTING_MODE == "chat_direct":
            return ClassificationResult(
                question_type="CHAT",
                confidence=1.0,
                reason="配置为直接聊天模式",
                method="direct_chat"
            )
        elif QUESTION_ROUTING_MODE == "llm_only":
            return self._enhanced_llm_classify(question)
        else:
            # hybrid模式：直接使用混合分类策略（规则+LLM）
            return self._hybrid_classify(question)

    def _hybrid_classify(self, question: str) -> ClassificationResult:
        """
        混合分类模式：规则预筛选 + 增强LLM分类
        这是原来的 classify 方法逻辑
        """
        # 第一步：规则预筛选
        rule_result = self._rule_based_classify(question)
        
        # 如果规则分类有高置信度，直接使用
        if rule_result.confidence >= self.high_confidence_threshold:
            return rule_result
        
        # 否则：使用增强的LLM分类
        llm_result = self._enhanced_llm_classify(question)
        
        # 选择置信度更高的结果
        if llm_result.confidence > rule_result.confidence:
            return llm_result
        else:
            return rule_result
    
    def _extract_current_question_for_rule_classification(self, question: str) -> str:
        """
        从enhanced_question中提取[CURRENT]部分用于规则分类
        如果没有[CURRENT]标签，返回原问题
        
        Args:
            question: 可能包含上下文的完整问题
            
        Returns:
            str: 用于规则分类的当前问题
        """
        try:
            # 处理None或非字符串输入
            if question is None:
                self.logger.warning("输入问题为None，返回空字符串")
                return ""
            
            if not isinstance(question, str):
                self.logger.warning(f"输入问题类型错误: {type(question)}，转换为字符串")
                question = str(question)
            
            # 检查是否为enhanced_question格式
            if "\n[CURRENT]\n" in question:
                current_start = question.find("\n[CURRENT]\n")
                if current_start != -1:
                    current_question = question[current_start + len("\n[CURRENT]\n"):].strip()
                    self.logger.info(f"规则分类从[CURRENT]标签提取到问题: {current_question}")
                    return current_question
            
            # 如果不是enhanced_question格式，直接返回原问题
            stripped_question = question.strip()
            self.logger.info(f"规则分类未找到[CURRENT]标签，使用完整问题: {stripped_question}")
            return stripped_question
            
        except Exception as e:
            self.logger.warning(f"提取当前问题失败: {str(e)}，返回空字符串")
            return ""

    def _rule_based_classify(self, question: str) -> ClassificationResult:
        """基于规则的预分类"""
        # 提取当前问题用于规则判断，避免上下文干扰
        current_question = self._extract_current_question_for_rule_classification(question)
        question_lower = current_question.lower()
        
        # 检查非业务实体词
        non_business_matched = []
        for keyword in self.non_business_keywords:
            if keyword in question_lower:
                non_business_matched.append(keyword)
        
        # 如果包含非业务实体词，直接分类为CHAT
        if non_business_matched:
            return ClassificationResult(
                question_type="CHAT",
                confidence=self.weights.get('non_business_confidence', 0.85),  # 使用YAML配置的置信度
                reason=f"包含非业务实体词: {non_business_matched}",
                method="rule_based_non_business"
            )
        
        # 检查强业务关键词
        business_score = 0
        business_matched = []
        
        for category, keywords in self.strong_business_keywords.items():
            if category == "系统查询指示词":  # 系统指示词单独处理
                continue
            for keyword in keywords:
                if keyword in question_lower:
                    business_score += self.weights.get('business_entity', 2)  # 使用YAML配置的权重
                    business_matched.append(f"{category}:{keyword}")
        
        # 检查系统查询指示词
        system_indicator_score = 0
        system_matched = []
        for keyword in self.strong_business_keywords.get("系统查询指示词", []):
            if keyword in question_lower:
                system_indicator_score += self.weights.get('system_indicator', 1)  # 使用YAML配置的权重
                system_matched.append(f"系统查询指示词:{keyword}")
        
        # 检查查询意图词
        intent_score = 0
        intent_matched = []
        for keyword in self.query_intent_keywords:
            if keyword in question_lower:
                intent_score += self.weights.get('query_intent', 1)  # 使用YAML配置的权重
                intent_matched.append(keyword)
        
        # 检查SQL模式
        sql_patterns_matched = []
        for pattern in self.sql_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                business_score += self.weights.get('sql_pattern', 3)  # 使用YAML配置的权重
                sql_patterns_matched.append(pattern)
        
        # 检查聊天关键词
        chat_score = 0
        chat_matched = []
        for keyword in self.chat_keywords:
            if keyword in question_lower:
                chat_score += self.weights.get('chat_keyword', 1)  # 使用YAML配置的权重
                chat_matched.append(keyword)
        
        # 系统指示词组合评分逻辑
        if system_indicator_score > 0 and business_score > 0:
            # 系统指示词 + 业务实体 = 强组合效应
            business_score += self.weights.get('combination_bonus', 3)  # 使用YAML配置的组合加分权重
            business_matched.extend(system_matched)
        elif system_indicator_score > 0:
            # 仅有系统指示词 = 中等业务倾向
            business_score += self.weights.get('system_indicator', 1)  # 使用YAML配置的权重
            business_matched.extend(system_matched)
        
        # 分类决策逻辑
        total_business_score = business_score + intent_score
        
        # 强业务特征：包含业务实体 + 查询意图
        min_business_score = self.weights.get('strong_business_min_score', 2)
        min_intent_score = self.weights.get('strong_business_min_intent', 1)
        if business_score >= min_business_score and intent_score >= min_intent_score:
            base_conf = self.weights.get('strong_business_base', 0.8)
            increment = self.weights.get('strong_business_increment', 0.05)
            confidence = min(self.max_confidence, base_conf + (total_business_score * increment))
            return ClassificationResult(
                question_type="DATABASE",
                confidence=confidence,
                reason=f"强业务特征 - 业务实体: {business_matched}, 查询意图: {intent_matched}, SQL: {sql_patterns_matched}",
                method="rule_based_strong_business"
            )
        
        # 中等业务特征：包含多个业务实体词
        elif business_score >= self.weights.get('medium_business_min_score', 4):
            base_conf = self.weights.get('medium_business_base', 0.7)
            increment = self.weights.get('medium_business_increment', 0.03)
            confidence = min(self.max_confidence, base_conf + (business_score * increment))
            return ClassificationResult(
                question_type="DATABASE", 
                confidence=confidence,
                reason=f"中等业务特征 - 业务实体: {business_matched}",
                method="rule_based_medium_business"
            )
        
        # 聊天特征
        elif chat_score >= self.weights.get('chat_min_score', 1) and business_score == 0:
            base_conf = self.weights.get('chat_base_confidence', 0.4)
            increment = self.weights.get('chat_confidence_increment', 0.08)
            confidence = min(self.max_confidence, base_conf + (chat_score * increment))
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
    
    def _load_business_context(self) -> str:
        """从文件中加载数据库业务范围描述"""
        try:
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_file = os.path.join(current_dir, "tools", "db_query_decision_prompt.txt")
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            if not content:
                raise ValueError("业务上下文文件为空")
                
            return content
            
        except FileNotFoundError:
            error_msg = f"无法找到业务上下文文件: {prompt_file}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        except Exception as e:
            error_msg = f"读取业务上下文文件失败: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _enhanced_llm_classify(self, question: str) -> ClassificationResult:
        """增强的LLM分类：包含详细的业务上下文"""
        try:
            from common.vanna_instance import get_vanna_instance
            vn = get_vanna_instance()
            
            # 动态加载业务上下文（如果失败会抛出异常）
            business_context = self._load_business_context()
            
            # 构建包含业务上下文的分类提示词
            classification_prompt = f"""
请判断以下用户问题是否需要查询我们的数据库。

用户问题：{question}

{business_context}

=== 判断标准 ===
1. **DATABASE类型** - 需要查询数据库：
   - 涉及上述业务实体和指标的查询、统计、分析、报表
   - 包含业务相关的时间查询
   - 例如：业务数据统计、收入排行、流量分析、占比分析等

2. **CHAT类型** - 不需要查询数据库：
   - 生活常识：水果蔬菜上市时间、动植物知识、天气等
   - 身份询问：你是谁、什么模型、AI助手等
   - 技术概念：人工智能、编程、算法等
   - 平台使用：功能介绍、操作帮助、使用教程等
   - 旅游出行：旅游景点、酒店、机票、高铁、的士等
   - 情绪：开心、伤心、无聊、生气、孤独、累了、烦恼、心情、难过、抑郁
   - 商业：股票、基金、理财、投资、经济、通货膨胀、上市
   - 哲学：人生意义、价值观、道德、信仰、宗教、爱情
   - 政策：政策、法规、法律、条例、指南、手册、规章制度、实施细则
   - 地理：全球、中国、亚洲、发展中、欧洲、美洲、东亚、东南亚、南美、非洲、大洋
   - 体育：足球、NBA、篮球、乒乓球、冠军、夺冠
   - 文学：小说、新闻、政治、战争、足球、NBA、篮球、乒乓球、冠军、夺冠
   - 娱乐：游戏、小说、新闻、政治、战争、足球、NBA、篮球、乒乓球、冠军、夺冠、电影、电视剧、音乐、舞蹈、绘画、书法、摄影、雕塑、建筑、设计、
   - 健康：健康、医疗、病症、健康、饮食、睡眠、心理、养生、减肥、美容、护肤
   - 其他：高考、人生意义、价值观、道德、信仰、宗教、爱情、全球、全国、亚洲、发展中、欧洲、美洲、东亚、东南亚、南美、非洲、大洋
   - 例如："荔枝几月份上市"、"今天天气如何"、"你是什么AI"、"怎么使用平台"

**重要提示：**
- 只有涉及高速公路服务区业务数据的问题才分类为DATABASE
- 只要不是涉及高速公路服务区业务数据的问题都应分类为CHAT

请基于问题与我们高速公路服务区业务数据的相关性来分类。

格式：
分类: [DATABASE/CHAT]
理由: [详细说明问题与业务数据的相关性，具体分析涉及哪些业务实体或为什么不相关]
置信度: [0.0-1.0之间的数字]
"""
            
            # 专业的系统提示词
            system_prompt = """你是一个专业的业务问题分类助手。你具有以下特长：
1. 深度理解业务领域和数据范围
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
            
        except (FileNotFoundError, RuntimeError) as e:
            # 业务上下文加载失败，返回错误状态
            self.logger.error(f"LLM分类失败，业务上下文不可用: {str(e)}")
            return ClassificationResult(
                question_type="CHAT",  # 失败时默认为CHAT，更安全
                confidence=self.weights.get('llm_error_confidence', 0.1),  # 使用YAML配置的低置信度
                reason=f"业务上下文加载失败，无法进行准确分类: {str(e)}",
                method="llm_context_error"
            )
        except Exception as e:
            self.logger.warning(f"增强LLM分类失败: {str(e)}")
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