-- 中文名: 路段路线与服务区关联表
-- 描述: 路段路线与服务区关联表，用于维护高速公路路段与其对应服务区的映射关系。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 服务区ID，主键,
  primary key (section_route_id, service_area_id)
);