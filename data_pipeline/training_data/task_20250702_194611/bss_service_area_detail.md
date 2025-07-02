## bss_service_area（存储高速公路服务区基础信息及管理记录）
bss_service_area 表存储高速公路服务区基础信息及管理记录，包含服务区名称、编码、创建/更新时间等，用于统一管理服务区数据。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人ID
- update_ts (timestamp) - 最后更新时间
- updated_by (varchar(50)) - 最后更新人ID
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人ID
- service_area_name (varchar(255)) - 服务区名称
- service_area_no (varchar(255)) - 服务区编码
- company_id (varchar(32)) - 所属公司ID
- service_position (varchar(255)) - 服务区经纬度
- service_area_type (varchar(50)) - 服务区类型
- service_state (varchar(50)) - 服务区状态
字段补充说明：
- id 为主键