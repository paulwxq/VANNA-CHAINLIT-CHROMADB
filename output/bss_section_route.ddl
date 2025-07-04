-- 中文名: 路段与路线关联配置表
-- 描述: 路段与路线关联配置表，存储路段名称与所属路线名称的对应关系，用于高速公路服务区的布局规划和路线管理。
create table public.bss_section_route (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建者,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新者,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除者,
  section_name varchar(255)   -- 路段名称,
  route_name varchar(255)     -- 路线名称,
  code varchar(255)           -- 编号,
  primary key (id)
);