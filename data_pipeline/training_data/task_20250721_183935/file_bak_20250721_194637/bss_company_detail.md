## bss_company（`bss_company` 表用于存储高速公路服务区相关企业的基本信息）
bss_company 表`bss_company` 表用于存储高速公路服务区相关企业的基本信息，包括公司名称和编码，支持服务区运营管理中的企业主体管理。
字段列表：
- id (varchar(32)) - 公司唯一标识 [主键, 非空] [示例: 30675d85ba5044c31acfa243b9d16334, 47ed0bb37f5a85f3d9245e4854959b81]
- version (integer) - 版本号 [非空] [示例: 1, 2]
- create_ts (timestamp) - 创建时间 [示例: 2021-05-20 09:51:58.718000, 2021-05-20 09:42:03.341000]
- created_by (varchar(50)) - 创建人 [示例: admin]
- update_ts (timestamp) - 更新时间 [示例: 2021-05-20 09:51:58.718000, 2021-05-20 09:42:03.341000]
- updated_by (varchar(50)) - 更新人 [示例: admin]
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- company_name (varchar(255)) - 公司名称 [示例: 上饶分公司, 宜春分公司, 景德镇分公司]
- company_no (varchar(255)) - 公司编码 [示例: H03, H02, H07]
字段补充说明：
- id 为主键
- company_name 为枚举字段，包含取值：抚州分公司、赣州分公司、吉安分公司、景德镇分公司、九江分公司、南昌分公司、其他公司管辖、上饶分公司、宜春分公司
- company_no 为枚举字段，包含取值：H01、H02、H03、H04、H05、H06、H07、H08、Q01