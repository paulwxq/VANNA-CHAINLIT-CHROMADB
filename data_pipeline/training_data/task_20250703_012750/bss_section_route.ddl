-- 中文名: 存储路段与路线信息
-- 描述: 存储路段与路线信息，支撑测试流程完整执行，记录操作日志
create table public.bss_section_route (
  id varchar(32) not null     -- 主键标识符，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  section_name varchar(255)   -- 路段名称,
  route_name varchar(255)     -- 路线名称,
  code varchar(255)           -- 编号,
  primary key (id)
);