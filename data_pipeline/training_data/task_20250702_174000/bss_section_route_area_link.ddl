-- 中文名: BSS系统路线分段与服务区关联表
-- 描述: BSS系统路线分段与服务区关联表，记录路线分段与服务区的绑定关系，支撑收费及服务设施管理。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 关联服务区ID，主键,
  primary key (section_route_id, service_area_id)
);