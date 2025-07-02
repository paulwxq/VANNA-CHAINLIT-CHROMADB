-- 中文名: 存储路段与路线关联关系及操作记录（共20字）
-- 描述: 存储路段与路线关联关系及操作记录（共20字）
create table public.bss_section_route (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
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