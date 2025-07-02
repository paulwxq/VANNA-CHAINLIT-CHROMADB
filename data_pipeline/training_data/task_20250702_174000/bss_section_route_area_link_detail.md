## bss_section_route_area_link（BSS系统路线分段与服务区关联表）
bss_section_route_area_link 表BSS系统路线分段与服务区关联表，记录路线分段与服务区的绑定关系，支撑收费及服务设施管理。
字段列表：
- section_route_id (varchar(32)) - 路段路线ID [主键, 非空]
- service_area_id (varchar(32)) - 关联服务区ID [主键, 非空]
字段补充说明：
- 复合主键：section_route_id, service_area_id