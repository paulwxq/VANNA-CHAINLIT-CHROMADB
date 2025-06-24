## bss_section_route（路段与路线关联配置表）
bss_section_route 表路段与路线关联配置表，存储路段名称与所属路线名称的对应关系，用于高速公路服务区的布局规划和路线管理。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 04ri3j67a806uw2c6o6dwdtz4knexczh, 0g5mnefxxtukql2cq6acul7phgskowy7]
- version (integer) - 版本号 [非空] [示例: 1, 0]
- create_ts (timestamp) - 创建时间 [示例: 2021-10-29 19:43:50, 2022-03-04 16:07:16]
- created_by (varchar(50)) - 创建者 [示例: admin]
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新者
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除者
- section_name (varchar(255)) - 路段名称 [示例: 昌栗, 昌宁]
- route_name (varchar(255)) - 路线名称 [示例: 昌栗, 昌韶]
- code (varchar(255)) - 编号 [示例: SR0001, SR0002]
字段补充说明：
- id 为主键