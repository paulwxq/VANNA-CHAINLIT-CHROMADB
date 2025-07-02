## bss_business_day_data（业务支撑系统每日业务统计表）
bss_business_day_data 表业务支撑系统每日业务统计表
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空]
- version (integer) - 版本号 [非空]
- create_ts (timestamp) - 创建时间
- created_by (varchar(50)) - 创建人
- update_ts (timestamp) - 更新时间
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- oper_date (date) - 统计日期
- service_no (varchar(255)) - 服务区编码
- service_name (varchar(255)) - 服务区名称
- branch_no (varchar(255)) - 档口编码
- branch_name (varchar(255)) - 档口名称
- wx (numeric(19,4)) - 微信支付金额
- wx_order (integer) - 微信订单数量
- zfb (numeric(19,4)) - 支付宝支付金额
- zf_order (integer) - 支付宝订单数量
- rmb (numeric(19,4)) - 现金支付金额
- rmb_order (integer) - 现金支付订单数量
- xs (numeric(19,4)) - 行吧支付金额
- xs_order (integer) - 行吧支付订单数
- jd (numeric(19,4)) - 金豆支付金额
- jd_order (integer) - 金豆支付订单数
- order_sum (integer) - 订单总数
- pay_sum (numeric(19,4)) - 支付总金额
- source_type (integer) - 数据来源类型
字段补充说明：
- id 为主键