## bss_car_day_count（`车辆日统计表：按类别统计服务区每日车流量）
bss_car_day_count 表`车辆日统计表：按类别统计服务区每日车流量，支撑运营分析与资源调度`
字段列表：
- id (varchar(32)) - 记录ID [主键, 非空]
- version (integer) - 数据版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- customer_count (bigint) - 车辆数量
- car_type (varchar(100)) - 车辆类别
- count_date (date) - 统计日期
- service_area_id (varchar(32)) - 服务区ID
字段补充说明：
- id 为主键