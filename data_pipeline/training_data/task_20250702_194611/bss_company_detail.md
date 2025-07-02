## bss_company（服务区公司信息表）
bss_company 表服务区公司信息表，存储运营主体基础数据，支持公司编码、名称及变更记录管理。
字段列表：
- id (varchar(32)) - 公司ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人ID
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人ID
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人ID
- company_name (varchar(255)) - 公司名称
- company_no (varchar(255)) - 公司编码
字段补充说明：
- id 为主键