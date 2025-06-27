## bss_section_route（记录路段与路线关联信息及版本变更）
bss_section_route 表记录路段与路线关联信息及版本变更，支持服务区运营管理（BSS系统核心配置表）
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 04ri3j67a806uw2c6o6dwdtz4knexczh, 0g5mnefxxtukql2cq6acul7phgskowy7]
- version (integer) - 版本号 [非空] [示例: 1, 0]
- create_ts (timestamp) - 创建时间 [示例: 2021-10-29 19:43:50, 2022-03-04 16:07:16]
- created_by (varchar(50)) - 创建人 [示例: admin]
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- section_name (varchar(255)) - 路段名称 [示例: 昌栗, 昌宁]
- route_name (varchar(255)) - 路线名称 [示例: 昌栗, 昌韶]
- code (varchar(255)) - 路段编号 [示例: SR0001, SR0002]
字段补充说明：
- id 为主键