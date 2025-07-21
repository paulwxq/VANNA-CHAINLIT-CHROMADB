-- 中文名: `bss_company` 表用于存储高速公路服务区相关公司的基本信息
-- 描述: `bss_company` 表用于存储高速公路服务区相关公司的基本信息，包括公司名称、编码及操作记录，支撑服务区运营管理。
create table public.bss_company (
  id varchar(32) not null     -- 公司ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  company_name varchar(255)   -- 公司名称,
  company_no varchar(255)     -- 公司编码,
  primary key (id)
);