## bss_business_day_data（高速公路服务区每日经营数据记录表）
bss_business_day_data 表高速公路服务区每日经营数据记录表，用于统计各服务区按日维度的运营情况。
字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 00827DFF993D415488EA1F07CAE6C440, 00e799048b8cbb8ee758eac9c8b4b820]
- version (integer) - 数据版本号 [非空] [示例: 1]
- create_ts (timestamp) - 创建时间 [示例: 2023-04-02 08:31:51, 2023-04-02 02:30:08]
- created_by (varchar(50)) - 创建人 [示例: xingba]
- update_ts (timestamp) - 更新时间 [示例: 2023-04-02 08:31:51, 2023-04-02 02:30:08]
- updated_by (varchar(50)) - 更新人
- delete_ts (timestamp) - 删除时间
- deleted_by (varchar(50)) - 删除人
- oper_date (date) - 统计日期 [示例: 2023-04-01]
- service_no (varchar(255)) - 服务区编码 [示例: 1028, H0501]
- service_name (varchar(255)) - 服务区名称 [示例: 宜春服务区, 庐山服务区]
- branch_no (varchar(255)) - 档口编码 [示例: 1, H05016]
- branch_name (varchar(255)) - 档口名称 [示例: 宜春南区, 庐山鲜徕客东区]
- wx (numeric(19,4)) - 微信支付金额 [示例: 4790.0000, 2523.0000]
- wx_order (integer) - 微信订单数量 [示例: 253, 133]
- zfb (numeric(19,4)) - 支付宝支付金额 [示例: 229.0000, 0.0000]
- zf_order (integer) - 支付宝订单数量 [示例: 15, 0]
- rmb (numeric(19,4)) - 现金支付金额 [示例: 1058.5000, 124.0000]
- rmb_order (integer) - 现金订单数量 [示例: 56, 12]
- xs (numeric(19,4)) - 行吧支付金额 [示例: 0.0000, 40.0000]
- xs_order (integer) - 行吧支付订单数 [示例: 0, 1]
- jd (numeric(19,4)) - 金豆支付金额 [示例: 0.0000]
- jd_order (integer) - 金豆支付订单数 [示例: 0]
- order_sum (integer) - 订单总数 [示例: 324, 146]
- pay_sum (numeric(19,4)) - 总支付金额 [示例: 6077.5000, 2687.0000]
- source_type (integer) - 数据来源类别 [示例: 1, 0, 4]
字段补充说明：
- id 为主键
- source_type 为枚举字段，包含取值：0、4、1、2、3