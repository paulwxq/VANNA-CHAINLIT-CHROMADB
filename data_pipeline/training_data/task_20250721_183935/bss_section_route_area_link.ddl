-- 中文名: 高速公路路段与服务区关联表
-- 描述: 高速公路路段与服务区关联表，用于管理路线和服务区的对应关系。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线唯一标识，主键,
  service_area_id varchar(32) not null -- 服务区唯一标识，主键,
  primary key (section_route_id, service_area_id)
);