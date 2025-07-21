-- 中文名: 路段路线信息表
-- 描述: 路段路线信息表，记录服务区所属路段及路线名称，支撑高速路网运营管理。
create table public.bss_section_route (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 数据版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  section_name varchar(255)   -- 路段名称,
  route_name varchar(255)     -- 路线名称,
  code varchar(255)           -- 路段编号,
  primary key (id)
);