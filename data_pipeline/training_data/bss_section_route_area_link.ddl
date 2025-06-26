-- 中文名: 记录路段路线与服务区的绑定关系
-- 描述: 记录路段路线与服务区的绑定关系，用于路径导航及服务区资源管理。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 服务区ID，主键,
  primary key (section_route_id, service_area_id)
);