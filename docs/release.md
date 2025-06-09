1.增加了开关 REWRITE_QUESTION_ENABLED = False，用于控制是否启用问题重写功能，也就是上下文问题合并。
"I interpreted your question as"


2.增加了开关 ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True，用于控制是否启用向量查询结果得分阈值过滤。

# 是否启用向量查询结果得分阈值过滤
# result = max((n + 1) // 2, 1)
ENABLE_RESULT_VECTOR_SCORE_THRESHOLD = True
# 向量查询结果得分阈值
RESULT_VECTOR_SQL_SCORE_THRESHOLD = 0.65
RESULT_VECTOR_DDL_SCORE_THRESHOLD = 0.5
RESULT_VECTOR_DOC_SCORE_THRESHOLD = 0.5

