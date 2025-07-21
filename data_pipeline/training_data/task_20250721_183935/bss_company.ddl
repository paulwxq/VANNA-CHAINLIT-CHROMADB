-- 中文名: 高速公路服务区管理系统中的公司信息表
-- 描述: 高速公路服务区管理系统中的公司信息表，存储服务区所属公司的基本信息及变更记录。
create table public.bss_company (
  id varchar(32) not null     -- 公司唯一标识符，主键,
  version integer not null    -- 数据版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除操作人,
  company_name varchar(255)   -- 公司名称,
  company_no varchar(255)     -- 公司编码,
  primary key (id)
);