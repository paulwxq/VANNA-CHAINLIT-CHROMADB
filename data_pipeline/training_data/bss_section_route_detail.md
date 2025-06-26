## bss_section_route（业务支撑系统路段与路线基础信息表）
bss_section_route 表业务支撑系统路段与路线基础信息表
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 04ri3j67a806uw2c6o6dwdtz4knexczh, 0g5mnefxxtukql2cq6acul7phgskowy7]
- version (integer) - 数据版本号 [非空] [示例: 1, 0]
- create_ts (timestamp) - 创建时间戳 [示例: 2021-10-29 19:43:50, 2022-03-04 16:07:16]
- created_by (varchar(50)) - 创建人标识 [示例: admin]
- update_ts (timestamp) - 最后更新时间
- updated_by (varchar(50)) - 最后更新人
- delete_ts (timestamp) - 删除时间戳
- deleted_by (varchar(50)) - 删除操作人
- section_name (varchar(255)) - 所属路段名称 [示例: 昌栗, 昌宁]
- route_name (varchar(255)) - 关联路线名称 [示例: 昌栗, 昌韶]
- code (varchar(255)) - 路段编码编号 [示例: SR0001, SR0002]
字段补充说明：
- id 为主键