## bss_service_area_mapper（记录BSS与服务区编码的映射关系）
bss_service_area_mapper 表记录BSS与服务区编码的映射关系，包含版本、维护人及状态，用于跨系统数据同步。
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
- source_system_type (varchar(50)) - 数据来源系统类型
- source_type (integer) - 数据来源类别ID
字段补充说明：
- id 为主键