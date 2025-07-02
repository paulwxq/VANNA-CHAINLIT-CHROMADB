-- 中文名: 业务支撑系统公司信息表
-- 描述: 业务支撑系统公司信息表，存储服务区关联企业的基础信息及状态变更记录
create table public.bss_company (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人ID,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人ID,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人ID,
  company_name varchar(255)   -- 公司名称,
  company_no varchar(255)     -- 公司编码,
  primary key (id)
);