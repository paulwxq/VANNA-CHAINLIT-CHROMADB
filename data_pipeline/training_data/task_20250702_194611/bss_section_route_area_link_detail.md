## bss_section_route_area_link（存储路线段与服务区关联关系）
bss_section_route_area_link 表存储路线段与服务区关联关系，管理高速线路与服务区归属
字段列表：
- section_route_id (varchar(32)) - 路段路线ID [主键, 非空]
- service_area_id (varchar(32)) - 服务区编码 [主键, 非空]
字段补充说明：
- 复合主键：section_route_id, service_area_id