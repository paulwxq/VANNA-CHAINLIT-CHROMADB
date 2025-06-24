-- 中文名: 表注释：高速公路服务区每日车辆通行统计及类型分析表
-- 描述: 表注释：高速公路服务区每日车辆通行统计及类型分析表
create table public.bss_car_day_count (
  id varchar(32) not null     -- 主键标识，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人ID,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人ID,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人ID,
  customer_count bigint       -- 车辆数量,
  car_type varchar(100)       -- 车辆类别,
  count_date date             -- 统计日期,
  service_area_id varchar(32) -- 服务区ID,
  primary key (id)
);