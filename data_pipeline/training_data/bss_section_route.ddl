-- 中文名: 业务支撑系统路段与路线基础信息表
-- 描述: 业务支撑系统路段与路线基础信息表
create table public.bss_section_route (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 数据版本号,
  create_ts timestamp         -- 创建时间戳,
  created_by varchar(50)      -- 创建人标识,
  update_ts timestamp         -- 最后更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间戳,
  deleted_by varchar(50)      -- 删除操作人,
  section_name varchar(255)   -- 所属路段名称,
  route_name varchar(255)     -- 关联路线名称,
  code varchar(255)           -- 路段编码编号,
  primary key (id)
);