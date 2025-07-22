## bss_service_area（高速公路服务区基础信息表）
bss_service_area 表高速公路服务区基础信息表，存储服务区名称、编码及管理元数据。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 0271d68ef93de9684b7ad8c7aae600b6, 08e01d7402abd1d6a4d9fdd5df855ef8]
- version (integer) - 版本号 [非空] [示例: 3, 6]
- create_ts (timestamp) - 创建时间 [示例: 2021-05-21 13:26:40.589000, 2021-05-20 19:51:46.314000]
- created_by (varchar(50)) - 创建人 [示例: admin]
- update_ts (timestamp) - 更新时间 [示例: 2021-07-10 15:41:28.795000, 2021-07-11 09:33:08.455000]
- updated_by (varchar(50)) - 更新人 [示例: admin]
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人 [示例: ]
- service_area_name (varchar(255)) - 服务区名称 [示例: 白鹭湖停车区, 南昌南服务区]
- service_area_no (varchar(255)) - 服务区编码 [示例: H0814, H0105]
- company_id (varchar(32)) - 所属公司ID [示例: b1629f07c8d9ac81494fbc1de61f1ea5, ee9bf1180a2b45003f96e597a4b7f15a]
- service_position (varchar(255)) - 服务区经纬度 [示例: 114.574721,26.825584, 115.910549,28.396355]
- service_area_type (varchar(50)) - 服务区类型 [示例: 信息化服务区]
- service_state (varchar(50)) - 服务区状态 [示例: 开放, 关闭]
字段补充说明：
- id 为主键
- service_area_type 为枚举字段，包含取值：信息化服务区、智能化服务区
- service_state 为枚举字段，包含取值：开放、关闭、上传数据