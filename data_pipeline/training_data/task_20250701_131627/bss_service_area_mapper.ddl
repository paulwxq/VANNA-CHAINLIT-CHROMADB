-- 中文名: BSS服务区基础信息映射表
-- 描述: BSS服务区基础信息映射表，记录服务区名称、编码及全生命周期操作日志
create table public.bss_service_area_mapper (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  service_name varchar(255)   -- 服务区名称,
  service_no varchar(255)     -- 服务区编码,
  service_area_id varchar(32) -- 服务区ID,
  source_system_type varchar(50) -- 数据来源系统类型,
  source_type integer         -- 数据来源类别ID,
  primary key (id)
);