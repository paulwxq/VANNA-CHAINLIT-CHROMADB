-- 中文名: 存储高速公路服务区基本信息（名称、编码等）
-- 描述: 存储高速公路服务区基本信息（名称、编码等），支持服务区运营管理。
create table public.bss_service_area (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人,
  update_ts timestamp         -- 最后更新时间,
  updated_by varchar(50)      -- 最后更新人,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除操作人,
  service_area_name varchar(255) -- 服务区名称,
  service_area_no varchar(255) -- 服务区编码,
  company_id varchar(32)      -- 所属公司ID,
  service_position varchar(255) -- 地理位置坐标,
  service_area_type varchar(50) -- 服务区类型,
  service_state varchar(50)   -- 服务区状态,
  primary key (id)
);