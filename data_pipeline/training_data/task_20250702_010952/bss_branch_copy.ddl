-- 中文名: 服务区档口基础信息表
-- 描述: 服务区档口基础信息表，包含档口ID、名称、编码及变更记录，用于管理服务区经营单元信息。
create table public.bss_branch_copy (
  id varchar(32) not null     -- 主键ID,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人账号,
  update_ts timestamp         -- 最后更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人账号,
  branch_name varchar(255)    -- 档口名称,
  branch_no varchar(255)      -- 档口编码,
  service_area_id varchar(32) -- 所属服务区ID,
  company_id varchar(32)      -- 所属公司ID,
  classify varchar(256)       -- 经营品类,
  product_brand varchar(256)  -- 经营品牌,
  category varchar(256)       -- 业态类别,
  section_route_id varchar(32) -- 所属线路ID,
  direction varchar(256)      -- 所在方位,
  is_manual_entry integer default 0 -- 数据录入方式,
  co_company varchar(256)     -- 合作经营单位
);