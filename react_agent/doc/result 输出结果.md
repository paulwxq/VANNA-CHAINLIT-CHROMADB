1.成功生成SQL并执行查询
POST  http://localhost:8084/api/v0/ask_agent 

{
    "question": "请按照收入给每个高速服务区进行排名？返回收入最多的前三名服务区？"
}


#正常生成SQL,并完成查询的返回结果

{
    "code": 200,
    "data": {
        "agent_version": "langgraph_v1",
        "classification_info": {
            "confidence": 0.9,
            "method": "rule_based_strong_business",
            "reason": "强业务特征 - 业务实体: ['核心业务实体:服务区', '支付业务:收入'], 查询意图: ['排名'], SQL: []"
        },
        "context_used": false,
        "conversation_id": "conv_1751199617_5d37a647",
        "conversation_message": "创建新对话",
        "conversation_status": "new",
        "execution_path": [
            "start",
            "classify",
            "agent_sql_generation",
            "agent_sql_execution",
            "format_response"
        ],
        "records": {
            "columns": [
                "服务区名称",
                "总收入"
            ],
            "is_limited": false,
            "row_count": 3,
            "rows": [
                {
                    "总收入": "7024226.1500",
                    "服务区名称": "庐山服务区"
                },
                {
                    "总收入": "6929288.3300",
                    "服务区名称": "三清山服务区"
                },
                {
                    "总收入": "6848435.6700",
                    "服务区名称": "南城服务区"
                }
            ],
            "total_row_count": 3
        },
        "response": "根据收入排名，前三名高速服务区依次为：庐山服务区（702.42万元）、三清山服务区（692.93万元）、南城服务区（684.84万元）。",
        "routing_mode_source": "config",
        "routing_mode_used": "hybrid",
        "session_id": null,
        "sql": "SELECT service_name AS 服务区名称, SUM(pay_sum) AS 总收入 \nFROM bss_business_day_data \nWHERE delete_ts IS NULL \nGROUP BY service_name \nORDER BY 总收入 DESC NULLS LAST \nLIMIT 3;",
        "summary": "根据收入排名，前三名高速服务区依次为：庐山服务区（702.42万元）、三清山服务区（692.93万元）、南城服务区（684.84万元）。",
        "timestamp": "2025-06-29T20:20:56.806141",
        "type": "DATABASE",

}

前端UI应关注的参数：
1."response": 它将代替原来的summary，会查询的结果进行总结。
2."sql"：执行查询SQL.
3."data.records"：查询返回的数据，包括表头(data.records.columns)和数据行(data.records.rows)


2.未成功生成SQL
POST  http://localhost:8084/api/v0/ask_agent 
{
    "question": "请问每个高速公路服务区的管理经理是谁？"
}


# 返回结果
{
    "code": 200,
    "data": {
        "agent_version": "langgraph_v1",
        "classification_info": {
            "confidence": 0.82,
            "method": "rule_based_medium_business",
            "reason": "中等业务特征 - 业务实体: ['核心业务实体:服务区', '核心业务实体:高速公路']"
        },
        "context_used": false,
        "conversation_id": "conv_1751201276_e59f0a07",
        "conversation_message": "创建新对话",
        "conversation_status": "new",
        "execution_path": [
            "start",
            "classify",
            "agent_sql_generation",
            "format_response"
        ],
        "response": "当前提供的上下文信息不足以生成查询服务区对应管理经理的SQL语句。原因如下：\n\n1. 在服务区管理公司表(bss_company)中虽然存在created_by/updated_by字段，但这些字段仅记录数据操作者（系统用户），而非实际的管理经理人员信息。\n\n2. 现有表结构中缺失以下关键实体：\n   - 员工/人员信息表（存储经理姓名等个人信息）\n   - 公司与人员的组织架构表（关联公司ID与员工ID）\n\n3. 当前表间关系仅能查询到服务区所属的管理公司名称（通过bss_service_area.company_id关联bss_company.id），但无法获取具体管理人员的姓名。\n\n需要补充以下信息才能继续：\n- 存储人员信息的表结构（特别是管理岗位人员）\n- 公司与人员的关联关系表结构 请尝试提问其它问题。",
        "routing_mode_source": "config",
        "routing_mode_used": "hybrid",
        "session_id": null,
        "timestamp": "2025-06-29T20:48:21.351324",
        "type": "DATABASE",
        "user_id": "guest"
    },
    "message": "操作成功",
    "success": true
}


前端UI应关注的参数：
1.没有返回"sql"和"data.records"。
2."response":当没有返回"sql"和"data.records"的时候，response会返回未能生成SQL的原因，可以返回给客户端

