## bss_service_area_mapper（BSS系统服务区名称与编码映射表）
bss_service_area_mapper 表BSS系统服务区名称与编码映射表，记录服务区基础信息及变更审计，支持统一管理和数据同步。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- service_name (varchar(255)) - 服务区名称
- service_no (varchar(255)) - 服务区编码
- service_area_id (varchar(32)) - 服务区ID
- source_system_type (varchar(50)) - 数据来源类别名称
- source_type (integer) - 数据来源类别ID
字段补充说明：
- id 为主键