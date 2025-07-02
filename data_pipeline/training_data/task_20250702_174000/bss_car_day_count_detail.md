## bss_car_day_count（每日服务区车辆类别数量统计表）
bss_car_day_count 表每日服务区车辆类别数量统计表，用于交通流量分析及资源调度管理
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
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