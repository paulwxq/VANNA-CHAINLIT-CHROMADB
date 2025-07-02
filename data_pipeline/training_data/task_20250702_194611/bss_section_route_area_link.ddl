-- 中文名: 存储路线段与服务区关联关系
-- 描述: 存储路线段与服务区关联关系，管理高速线路与服务区归属
create table public.bss_section_route_area_link (
  section_route_id varchar(32) not null -- 路段路线ID，主键,
  service_area_id varchar(32) not null -- 服务区编码，主键,
  primary key (section_route_id, service_area_id)
);