## bss_service_area（业务支撑系统服务区主表）
bss_service_area 表业务支撑系统服务区主表，存储名称、编码等基础信息，支撑服务区运营管理。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人ID
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人ID
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人ID
- service_area_name (varchar(255)) - 服务区名称
- service_area_no (varchar(255)) - 服务区编码
- company_id (varchar(32)) - 运营管理公司ID
- service_position (varchar(255)) - 地理位置坐标
- service_area_type (varchar(50)) - 服务区类型
- service_state (varchar(50)) - 运营状态
字段补充说明：
- id 为主键