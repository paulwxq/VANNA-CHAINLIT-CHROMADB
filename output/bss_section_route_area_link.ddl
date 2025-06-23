-- 中文名: 路线与服务区关联表
-- 描述: 路线与服务区关联表
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 服务区ID，主键,
  primary key (section_route_id, service_area_id)
);