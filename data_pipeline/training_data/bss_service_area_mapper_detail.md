## bss_service_area_mapper（服务区名称与编码映射表）
bss_service_area_mapper 表服务区名称与编码映射表，记录基础信息及变更记录，支撑服务区业务数据关联
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 00e1e893909211ed8ee6fa163eaf653f, 013867f5962211ed8ee6fa163eaf653f]
- version (integer) - 版本号 [非空] [示例: 1]
- create_ts (timestamp) - 创建时间 [示例: 2023-01-10 10:54:03, 2023-01-17 12:47:29]
- created_by (varchar(50)) - 创建人 [示例: admin]
- update_ts (timestamp) - 更新时间 [示例: 2023-01-10 10:54:07, 2023-01-17 12:47:32]
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- service_name (varchar(255)) - 服务区名称 [示例: 信丰西服务区, 南康北服务区]
- service_no (varchar(255)) - 服务区编码 [示例: 1067, 1062]
- service_area_id (varchar(32)) - 服务区ID [示例: 97cd6cd516a551409a4d453a58f9e170, fdbdd042962011ed8ee6fa163eaf653f]
- source_system_type (varchar(50)) - 数据来源系统类型 [示例: 驿美, 驿购]
- source_type (integer) - 数据来源类别ID [示例: 3, 1]
字段补充说明：
- id 为主键
- source_system_type 为枚举字段，包含取值：司乘管理、商业管理、驿购、驿美、手工录入