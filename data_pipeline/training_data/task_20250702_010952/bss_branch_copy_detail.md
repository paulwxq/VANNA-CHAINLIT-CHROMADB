## bss_branch_copy（服务区档口基础信息表）
bss_branch_copy 表服务区档口基础信息表，包含档口ID、名称、编码及变更记录，用于管理服务区经营单元信息。
字段列表：
- id (varchar(32)) - 主键ID [非空] [示例: 00904903cae681aab7a494c3e88e5acd, 01a3df15b454fa7b5f176125af0c57d8]
- version (integer) - 版本号 [非空] [示例: 1]
- create_ts (timestamp) - 创建时间 [示例: 2021-10-15 09:46:45.010000, 2021-05-20 19:53:58.977000]
- created_by (varchar(50)) - 创建人账号 [示例: admin]
- update_ts (timestamp) - 最后更新时间 [示例: 2021-10-15 09:46:45.010000, 2021-11-07 20:26:10]
- updated_by (varchar(50)) - 最后更新人 [示例: updated by importSQL]
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人账号
- branch_name (varchar(255)) - 档口名称 [示例: 于都驿美餐饮南区, 南城餐饮西区]
- branch_no (varchar(255)) - 档口编码 [示例: 003585, H0601B]
- service_area_id (varchar(32)) - 所属服务区ID [示例: c7e2f26df373e9cb75bd24ddba57f27f, 8eb8ec693642354a62d640c7f1c2365c]
- company_id (varchar(32)) - 所属公司ID [示例: ce5e6f553513dad393694e1fa663aaf4, e6c060f05306a03f978e2b952a551744]
- classify (varchar(256)) - 经营品类 [示例: 餐饮, 小吃, 其他]
- product_brand (varchar(256)) - 经营品牌 [示例: 驿美餐饮, 小圆满（自助餐）]
- category (varchar(256)) - 业态类别 [示例: 餐饮, 中餐, 小吃]
- section_route_id (varchar(32)) - 所属线路ID [示例: lvkcuu94d4487c42z7qltsvxcyz0iqu5, wnejyryq6zvtdy6axgvz6jutv8n6vc3r]
- direction (varchar(256)) - 所在方位 [示例: 南区, 西区, 北区]
- is_manual_entry (integer) - 数据录入方式 [示例: 0]
- co_company (varchar(256)) - 合作经营单位 [示例: 江西驿美餐饮管理有限责任公司, 嘉兴市同辉高速公路服务区经营管理有限公司]
字段补充说明：
- classify 为枚举字段，包含取值：其他、小吃、餐饮、便利店、整体租赁
- direction 为枚举字段，包含取值：南区、东区、北区、西区、、两区
- is_manual_entry 为枚举字段，包含取值：0、1