-- 中文名: 记录高速公路路段路线与服务区的关联关系
-- 描述: 记录高速公路路段路线与服务区的关联关系，支撑路线规划与服务区运营管理。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 服务区ID，主键,
  primary key (section_route_id, service_area_id)
);