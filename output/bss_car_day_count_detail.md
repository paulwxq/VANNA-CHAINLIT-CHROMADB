## bss_car_day_count（表注释：高速公路服务区每日车辆通行统计及类型分析表）
bss_car_day_count 表表注释：高速公路服务区每日车辆通行统计及类型分析表
字段列表：
- id (varchar(32)) - 主键标识 [主键, 非空] [示例: 00022c1c99ff11ec86d4fa163ec0f8fc, 00022caa99ff11ec86d4fa163ec0f8fc]
- version (integer) - 版本号 [非空] [示例: 1]
- create_ts (timestamp) - 创建时间 [示例: 2022-03-02 16:01:43, 2022-02-02 14:18:55]
- created_by (varchar(50)) - 创建人ID
- update_ts (timestamp) - 更新时间 [示例: 2022-03-02 16:01:43, 2022-02-02 14:18:55]
- updated_by (varchar(50)) - 更新人ID
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人ID
- customer_count (bigint) - 车辆数量 [示例: 1114, 295]
- car_type (varchar(100)) - 车辆类别 [示例: 其他]
- count_date (date) - 统计日期 [示例: 2022-03-02, 2022-02-02]
- service_area_id (varchar(32)) - 服务区ID [示例: 17461166e7fa3ecda03534a5795ce985, 81f4eb731fb0728aef17ae61f1f1daef]
字段补充说明：
- id 为主键
- car_type 为枚举字段，包含取值：其他、危化品、城际、过境