# 关于Metadata.txt产生的修改需求



### 一、主要修改内容概述：

- 修改metadata表结构；
- 修改metadata.txt中的建表语句和插入语句；
- 为metadata表创建一个md文件；
- 新增一个 db_query_decision_prompt.txt 文件。

### 二、修改详细需求如下：

### 1.修改 metadata 表结构：

- 把原来的字段 keywords 改为业务实体  biz_entities，类型不变
- 把原来的字段 foceus_area 改为业务指标 biz_metrics ，类型不变。

```sql
CREATE TABLE IF NOT EXISTS metadata (
    id SERIAL PRIMARY KEY,    -- 主键
    topic_name VARCHAR(100) NOT NULL,  -- 业务主题名称
    description TEXT,                  -- 业务主体说明
    related_tables TEXT[],			  -- 相关表名
    biz_entities TEXT[],               -- 主要业务实体名称
    biz_metrics TEXT[],                -- 主要业务指标名称
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP    -- 插入时间
);
```

### 2.在生成 metadata.txt 的时候，文件的内容也要相应的修改：

- 创建表的sql语句(create table metadata)需要更新为上面的内容。
- 生成的数据也要适应上面的要求，比如 biz_entities，它主要是表的维度(dim)字段，或者说非数值型字段。
- biz_metrics 主要是指统计指标(metrics)的名称。
- insert into metadata语句也要做相应的调整。

### 3.为metadata.txt表生成一个md文件：

格式请参考下面的内容，其实下面只要修改这个表的字段后的“示例”和"例如"就可以了，其他基本不用修改。

### metadata（存储分析主题元数据）

`metadata` 主要描述了当前数据库包含了哪些数据内容，哪些分析主题，哪些指标等等。

字段列表：

- `id` (serial) - 主键ID [主键, 非空]
- `topic_name` (varchar(100)) - 业务主题名称 [非空]
- `description` (text) - 业务主题说明
- `related_tables` (text[]) - 涉及的数据表 [示例: `{bss_business_day_data, bss_service_area}`]
- `biz_entities` (text[]) - 主要业务实体名称 [示例: `{营收, 服务区, 支付方式}`]
- `biz_metrics` (text[]) - 主要业务指标名称 [示例: `{收入趋势, 支付方式分布, 服务区对比}`]
- `created_at` (timestamp) - 插入时间 [默认值: `CURRENT_TIMESTAMP`]

字段补充说明：

- `id` 为主键，自增；
- `related_tables` 用于建立主题与具体明细表的依赖关系；
- `biz_entities` 表示主题关注的核心对象，例如服务区、车辆、公司；
- `biz_metrics` 表示该主题关注的业务分析指标，例如营收对比、趋势变化、占比结构等。

### 4.新增一个文本文件 db_query_decision_prompt.txt

该文件存储的是用于LLM判断是查询数据库，还是自由对话的提示词，请再提交LLM生成metadata.txt的内容时，同步生成这个文件，它的格式如下：

```
=== 数据库业务范围 ===
当前数据库存储的是高速公路服务区的相关数据，主要涉及服务区、管理公司等主题，包含以下业务数据：
核心业务实体：
- 服务区：服务区基础信息、位置、状态，如"鄱阳湖服务区"、"信丰西服务区"
- 档口/商铺：档口信息、品类(餐饮/小吃/便利店)、品牌，如"驿美餐饮"、"加水机"
- 营业数据：每日支付金额、订单数量，包含微信、支付宝、现金等支付方式
关键业务指标：
- 支付方式：微信支付(wx)、支付宝支付(zfb)、现金支付(rmb)、行吧支付(xs)、金豆支付(jd)
- 营业数据：支付金额、订单数量、营业额、收入统计
```

### 三、补充说明

 db_query_decision_prompt.txt 和 metadata.txt 其实只是表现形式不同，可以让大模型同时生成。