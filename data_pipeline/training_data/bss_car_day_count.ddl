-- 中文名: 服务区车辆类型日统计表
-- 描述: 服务区车辆类型日统计表，记录每日车流数量及分类数据，用于交通流量分析与服务资源调度。
create table public.bss_car_day_count (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  customer_count bigint       -- 车辆数量,
  car_type varchar(100)       -- 车辆类型,
  count_date date             -- 统计日期,
  service_area_id varchar(32) -- 服务区ID,
  primary key (id)
);