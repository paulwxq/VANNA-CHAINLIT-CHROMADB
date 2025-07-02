-- 中文名: 业务支撑系统公司信息表
-- 描述: 业务支撑系统公司信息表，记录公司基础信息及创建/更新/删除操作痕迹。
create table public.bss_company (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 最后更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  company_name varchar(255)   -- 公司名称,
  company_no varchar(255)     -- 公司编码,
  primary key (id)
);