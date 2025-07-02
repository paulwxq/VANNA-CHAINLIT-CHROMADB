-- 中文名: 存储服务区基础信息
-- 描述: 存储服务区基础信息，包含名称、编码及操作记录，支撑业务区域管理
create table public.bss_service_area (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人,
  service_area_name varchar(255) -- 服务区名称,
  service_area_no varchar(255) -- 服务区编码,
  company_id varchar(32)      -- 所属公司ID,
  service_position varchar(255) -- 地理坐标,
  service_area_type varchar(50) -- 服务区类型,
  service_state varchar(50)   -- 运营状态,
  primary key (id)
);