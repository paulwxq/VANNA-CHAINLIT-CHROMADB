## bss_section_route_area_link（路线分段与服务区关联表）
bss_section_route_area_link 表路线分段与服务区关联表，记录路线与服务区的对应关系
字段列表：
- section_route_id (varchar(32)) - 路段路线ID [主键, 非空] [示例: v8elrsfs5f7lt7jl8a6p87smfzesn3rz, hxzi2iim238e3s1eajjt1enmh9o4h3wp]
- service_area_id (varchar(32)) - 服务区ID [主键, 非空] [示例: 08e01d7402abd1d6a4d9fdd5df855ef8, 091662311d2c737029445442ff198c4c]
字段补充说明：
- 复合主键：section_route_id, service_area_id