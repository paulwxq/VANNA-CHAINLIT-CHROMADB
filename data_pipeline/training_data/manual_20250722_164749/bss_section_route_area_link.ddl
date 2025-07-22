-- 中文名: 高速公路服务区与路线关联表
-- 描述: 高速公路服务区与路线关联表，记录服务区所属路段关系。
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线唯一标识，主键,
  service_area_id varchar(32) not null -- 服务区唯一标识，主键,
  primary key (section_route_id, service_area_id)
);