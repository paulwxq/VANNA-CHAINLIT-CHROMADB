## metadata（存储分析主题元数据）

`metadata` 主要描述了当前数据库包含了哪些数据内容，哪些分析主题，哪些指标等等。

字段列表：

- `id` (serial) - 主键ID [主键, 非空]
- `topic_name` (varchar(100)) - 业务主题名称 [非空]
- `description` (text) - 业务主题说明
- `related_tables` (text[]) - 涉及的数据表 [示例: bss_car_day_count, bss_section_route]
- `biz_entities` (text[]) - 主要业务实体名称 [示例: 路段, 车辆类型, 档口]
- `biz_metrics` (text[]) - 主要业务指标名称 [示例: 营收排名, 时段波动, 消费热度]
- `created_at` (timestamp) - 插入时间 [默认值: `CURRENT_TIMESTAMP`]

字段补充说明：

- `id` 为主键，自增；
- `related_tables` 用于建立主题与具体明细表的依赖关系；
- `biz_entities` 表示主题关注的核心对象，例如服务区、车辆、公司；
- `biz_metrics` 表示该主题关注的业务分析指标，例如营收对比、趋势变化、占比结构等。
