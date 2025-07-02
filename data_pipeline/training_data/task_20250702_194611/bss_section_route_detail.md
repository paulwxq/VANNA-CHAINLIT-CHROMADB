## bss_section_route（业务支撑系统路段路线关联表）
bss_section_route 表业务支撑系统路段路线关联表，记录路段与路线名称对应关系，用于服务区位置管理及路网信息维护
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- section_name (varchar(255)) - 路段名称
- route_name (varchar(255)) - 路线名称
- code (varchar(255)) - 编号
字段补充说明：
- id 为主键