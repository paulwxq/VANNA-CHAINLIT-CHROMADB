-- 中文名: BSS服务区信息映射表
-- 描述: BSS服务区信息映射表，记录服务区名称、编码及版本操作记录
create table public.bss_service_area_mapper (
  id varchar(32) not null     -- 主键标识符，主键,
  version integer not null    -- 记录版本号,
  create_ts timestamp         -- 记录创建时间,
  created_by varchar(50)      -- 记录创建人,
  update_ts timestamp         -- 最后更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间（软删除）,
  deleted_by varchar(50)      -- 软删除操作人,
  service_name varchar(255)   -- 服务区中文名称,
  service_no varchar(255)     -- 服务区编码编号,
  service_area_id varchar(32) -- 服务区唯一标识,
  source_system_type varchar(50) -- 数据来源系统类型,
  source_type integer         -- 数据来源类别代码,
  primary key (id)
);