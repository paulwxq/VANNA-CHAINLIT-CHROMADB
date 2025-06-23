# Redis缓存管理API完整文档

## 概述

辞图智能数据问答平台基于Redis实现了完整的缓存管理系统，包括**对话管理**、**问答缓存**、**Embedding向量缓存**等功能。本文档详细介绍了所有与Redis缓存相关的API接口。

## API基础信息

- **基础URL**: `http://localhost:8084`
- **Content-Type**: `application/json`
- **响应格式**: 标准化的JSON响应格式
- **Redis配置**: 通过 `app_config.py` 中的 `REDIS_*` 参数配置连接

## API分类目录

### 1. 对话管理API
- [获取用户对话列表](#获取用户对话列表)
- [获取对话消息历史](#获取对话消息历史)
- [获取对话上下文](#获取对话上下文)
- [获取用户完整对话数据](#获取用户完整对话数据)
- [获取对话系统统计](#获取对话系统统计)
- [清理过期对话](#清理过期对话)

### 2. 问答缓存管理API
- [获取问答缓存统计](#获取问答缓存统计)
- [获取问答缓存列表](#获取问答缓存列表)
- [清空问答缓存](#清空问答缓存)

### 3. Embedding向量缓存管理API
- [获取Embedding缓存统计](#获取embedding缓存统计)
- [清空Embedding缓存](#清空embedding缓存)

### 4. 智能问答API（使用Redis缓存）
- [智能问答（支持对话上下文）](#智能问答支持对话上下文)

### 5. 综合缓存管理API
- [获取综合缓存概览](#获取综合缓存概览)

---

## 详细API文档

### 对话管理API

#### 获取用户对话列表

**接口信息**
- **URL**: `/api/v0/user/{user_id}/conversations`
- **方法**: `GET`
- **功能**: 获取指定用户的对话列表，按时间倒序排列

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| user_id | string | 路径参数 | 是 | - | 用户ID |
| limit | integer | 查询参数 | 否 | USER_MAX_CONVERSATIONS | 最大返回数量 |

**请求示例**
```http
GET /api/v0/user/john_doe/conversations?limit=10
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取用户对话列表成功",
    "data": {
        "user_id": "john_doe",
        "conversations": [
            {
                "conversation_id": "conv_1703145600_abc123",
                "user_id": "john_doe",
                "created_at": "2024-12-22T10:00:00",
                "updated_at": "2024-12-22T10:30:00",
                "message_count": "6"
            }
        ],
        "total_count": 1
    }
}
```

---

#### 获取对话消息历史

**接口信息**
- **URL**: `/api/v0/conversation/{conversation_id}/messages`
- **方法**: `GET`
- **功能**: 获取特定对话的所有消息历史

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| conversation_id | string | 路径参数 | 是 | - | 对话ID |
| limit | integer | 查询参数 | 否 | 无限制 | 最大返回消息数量 |

**请求示例**
```http
GET /api/v0/conversation/conv_1703145600_abc123/messages?limit=20
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取对话消息成功",
    "data": {
        "conversation_id": "conv_1703145600_abc123",
        "conversation_meta": {
            "conversation_id": "conv_1703145600_abc123",
            "user_id": "john_doe",
            "created_at": "2024-12-22T10:00:00",
            "message_count": "6"
        },
        "messages": [
            {
                "message_id": "msg_uuid_1",
                "timestamp": "2024-12-22T10:00:00",
                "role": "user",
                "content": "查询最近一个月的销售数据",
                "metadata": {}
            },
            {
                "message_id": "msg_uuid_2",
                "timestamp": "2024-12-22T10:00:05",
                "role": "assistant",
                "content": "好的，我来为您查询最近一个月的销售数据...",
                "metadata": {
                    "type": "DATABASE",
                    "sql": "SELECT * FROM sales WHERE date >= DATE_SUB(NOW(), INTERVAL 1 MONTH)"
                }
            }
        ],
        "message_count": 2
    }
}
```

---

#### 获取对话上下文

**接口信息**
- **URL**: `/api/v0/conversation/{conversation_id}/context`
- **方法**: `GET`
- **功能**: 获取对话上下文（格式化用于LLM输入）

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| conversation_id | string | 路径参数 | 是 | - | 对话ID |
| count | integer | 查询参数 | 否 | CONVERSATION_CONTEXT_COUNT | 上下文消息条数 |

**请求示例**
```http
GET /api/v0/conversation/conv_1703145600_abc123/context?count=5
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取对话上下文成功",
    "data": {
        "conversation_id": "conv_1703145600_abc123",
        "context": "用户: 查询最近一个月的销售数据\n助手: 好的，我来为您查询最近一个月的销售数据...\n用户: 请按地区分类显示\n助手: 我来为您按地区分类显示销售数据...",
        "context_message_count": 5
    }
}
```

---

#### 获取用户完整对话数据

**接口信息**
- **URL**: `/api/v0/user/{user_id}/conversations/full`
- **方法**: `GET`
- **功能**: 一次性获取用户的所有对话和每个对话下的消息历史

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| user_id | string | 路径参数 | 是 | - | 用户ID |
| conversation_limit | integer | 查询参数 | 否 | 无限制 | 对话数量限制 |
| message_limit | integer | 查询参数 | 否 | 无限制 | 每个对话的消息数限制 |

**请求示例**
```http
GET /api/v0/user/paul/conversations/full?conversation_limit=50&message_limit=100
```

**响应示例**
```json
{
    "code": 200,
    "data": {
        "conversation_limit_applied": null,
        "conversations": [
            {
                "conversation_id": "conv_1750595305_dcf838e2",
                "created_at": "2025-06-22T20:28:25.818161",
                "message_count": 5,
                "messages": [
                    {
                        "content": "当前数据库高速公路管理公司最多管理几个服务区？",
                        "message_id": "4a31377c-c148-4834-bc76-2d1c414c1605",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:28:25.835622"
                    },
                    {
                        "content": "高速公路管理公司中，赣州分公司和吉安分公司管理的服务区最多，均为15个。",
                        "message_id": "b789076d-fca7-4978-80a0-e68c7174cc77",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT c.company_name, COUNT(DISTINCT sa.id) AS service_area_count \nFROM bss_company c \nJOIN bss_service_area sa ON c.id = sa.company_id \nWHERE c.delete_ts IS NULL AND sa.delete_ts IS NULL \nGROUP BY c.company_name \nORDER BY service_area_count DESC NULLS LAST;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T20:30:10.958259"
                    },
                    {
                        "content": "当前数据库档口有几种支付方式?",
                        "message_id": "a6822e0b-8545-4596-894b-f87453e88415",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:31:46.619330"
                    },
                    {
                        "content": "当前数据库档口有几种支付方式?",
                        "message_id": "b3239beb-0478-4ed5-8639-abe125896531",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:33:00.495390"
                    },
                    {
                        "content": "当前数据库档口共有5种支付方式，分别为：微信、支付宝、现金、行吧、金豆。",
                        "message_id": "2aa38c88-d6b4-4885-aba5-2e6113b1df17",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT unnest(array['微信', '支付宝', '现金', '行吧', '金豆']) AS payment_method;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T20:33:28.090739"
                    }
                ],
                "meta": {
                    "conversation_id": "conv_1750595305_dcf838e2",
                    "created_at": "2025-06-22T20:28:25.818161",
                    "message_count": "5",
                    "updated_at": "2025-06-22T20:33:28.098477",
                    "user_id": "paul"
                },
                "updated_at": "2025-06-22T20:33:28.098477",
                "user_id": "paul"
            },
            {
                "conversation_id": "conv_1750593645_ce3b0575",
                "created_at": "2025-06-22T20:00:45.705232",
                "message_count": 6,
                "messages": [
                    {
                        "content": "当前数据库高速公路服务区有几个管理公司？",
                        "message_id": "8bc39508-68d1-461e-8f96-8d2cc781f3cf",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:00:45.717241"
                    },
                    {
                        "content": "当前数据库中高速公路服务区有8个管理公司。",
                        "message_id": "f39b3afb-912b-4216-8d7f-67e464b05f36",
                        "metadata": {
                            "from_cache": true
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T20:00:45.722374"
                    },
                    {
                        "content": "当前数据库高速公路管理公司最多管理几个服务区？",
                        "message_id": "1bd12dbc-1598-45a6-a78a-d59ede093f65",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:02:43.530629"
                    },
                    {
                        "content": "赣州分公司最多管理15个服务区。",
                        "message_id": "1f8b0bea-2cbb-4052-af6d-f949f44d00ba",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT c.company_name AS 管理公司名称, COUNT(DISTINCT sa.id) AS 管辖服务区数量 \nFROM bss_company c \nJOIN bss_service_area sa ON c.id = sa.company_id \nWHERE c.delete_ts IS NULL AND sa.delete_ts IS NULL \nGROUP BY c.company_name \nORDER BY 管辖服务区数量 DESC NULLS LAST \nLIMIT 1;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T20:03:13.320058"
                    },
                    {
                        "content": "当前数据库高速公路管理公司最多管理几个服务区？",
                        "message_id": "62b71601-ae65-48b1-bcfd-66162f45982c",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T20:03:54.506039"
                    },
                    {
                        "content": "根据数据，高速公路管理公司最多管理的服务区数量为15个（赣州分公司）。",
                        "message_id": "3b04dc43-c7c2-4d98-813d-a80115963996",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT c.company_name AS 公司名称, COUNT(sa.id) AS 服务区数量 FROM bss_company c JOIN bss_service_area sa ON c.id = sa.company_id WHERE c.delete_ts IS NULL AND sa.delete_ts IS NULL GROUP BY c.company_name ORDER BY 服务区数量 DESC NULLS LAST LIMIT 1;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T20:04:16.205513"
                    }
                ],
                "meta": {
                    "conversation_id": "conv_1750593645_ce3b0575",
                    "created_at": "2025-06-22T20:00:45.705232",
                    "message_count": "6",
                    "updated_at": "2025-06-22T20:04:16.211064",
                    "user_id": "paul"
                },
                "updated_at": "2025-06-22T20:04:16.211064",
                "user_id": "paul"
            },
            {
                "conversation_id": "conv_1750593511_8828ee0c",
                "created_at": "2025-06-22T19:58:31.020583",
                "message_count": 2,
                "messages": [
                    {
                        "content": "当前数据库高速公路服务区有几个管理公司？",
                        "message_id": "c6b73d34-b6be-4bf6-8dae-a969971437c3",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T19:58:31.031194"
                    },
                    {
                        "content": "当前数据库中高速公路服务区有8个管理公司。",
                        "message_id": "38be0043-ad02-4d76-9c38-6be7750bec3f",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT COUNT(DISTINCT c.id) AS 管理公司数量 FROM bss_company c JOIN bss_service_area sa ON c.id = sa.company_id WHERE c.delete_ts IS NULL AND sa.delete_ts IS NULL;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T19:59:01.705833"
                    }
                ],
                "meta": {
                    "conversation_id": "conv_1750593511_8828ee0c",
                    "created_at": "2025-06-22T19:58:31.020583",
                    "message_count": "2",
                    "updated_at": "2025-06-22T19:59:01.709839",
                    "user_id": "paul"
                },
                "updated_at": "2025-06-22T19:59:01.709839",
                "user_id": "paul"
            },
            {
                "conversation_id": "conv_1750588941_6a14bbaa",
                "created_at": "2025-06-22T18:42:21.008532",
                "message_count": 17,
                "messages": [
                    {
                        "content": "请问河南的省会在哪里",
                        "message_id": "6f41173b-c2d6-495f-baba-d870707e1129",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:42:21.024871"
                    },
                    {
                        "content": "河南省的省会是郑州市。\n\n如果您需要了解其他省份的省会信息，或者想查询河南相关的经济、人口等数据，可以告诉我，我会为您调取相关数据报告哦！ 😊",
                        "message_id": "336d21ca-0ed8-4bc5-939d-9a33f85afc5a",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_chat",
                                "format_response"
                            ],
                            "sql": null,
                            "type": "CHAT"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:42:45.092210"
                    },
                    {
                        "content": "请问系统里的高速公路服务区共有多少个？",
                        "message_id": "39e76f77-47d0-420b-82bf-fba906e80aa2",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:43:27.881837"
                    },
                    {
                        "content": "系统内的高速公路服务区共有120个。",
                        "message_id": "24ca5abb-1f18-4d9b-875c-863e3805f9aa",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT COUNT(*) AS 服务区总数 FROM bss_service_area WHERE delete_ts IS NULL;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:43:51.261346"
                    },
                    {
                        "content": "请问系统里的高速公路服务区共有多少个？",
                        "message_id": "e042c5c5-e953-42b6-98b8-b7cf32fcc260",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:44:25.369663"
                    },
                    {
                        "content": "系统内的高速公路服务区共有120个。\n\n如果您需要查询具体的服务区分布或相关运营数据，也可以告诉我，我将为您生成详细的数据报告哦！ 📊",
                        "message_id": "d894e2cd-6fd1-4b59-8ff3-d7d6b36bcbb6",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "init_direct_chat",
                                "agent_chat",
                                "format_response"
                            ],
                            "sql": null,
                            "type": "CHAT"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:44:31.505382"
                    },
                    {
                        "content": "请问荔枝什么时候成熟？",
                        "message_id": "75235ad8-6b94-41ae-918d-af2af73f38f7",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:45:30.025243"
                    },
                    {
                        "content": "荔枝什么时候成熟？",
                        "message_id": "8eae8533-0449-43ff-a75b-b8c5a657b6c3",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:46:09.134119"
                    },
                    {
                        "content": "荔枝一般在每年的**6月至7月**进入成熟期，这是我国荔枝的主要上市季节。不过具体时间会因种植地区和气候条件有所差异，例如广东、广西等主产区可能会稍早一些，而福建等地可能稍晚。\n\n如果您想了解某个特定产地的荔枝成熟时间，或者需要相关产业数据（如产量、品种分布等），我可以为您生成详细的数据报告哦！ 🍌",
                        "message_id": "c519545a-3532-443a-804d-7c59f7155b94",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_chat",
                                "format_response"
                            ],
                            "sql": null,
                            "type": "CHAT"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:46:20.380136"
                    },
                    {
                        "content": "当前数据库中能查到几个经营公司？",
                        "message_id": "e91ca884-59c5-4014-93c7-8a5a5781d9ef",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:52:07.937590"
                    },
                    {
                        "content": "关于经营公司的数量，当前系统中暂未收录具体的经营主体数据。不过，我们可以通过高速公路服务区数据进行关联分析——已知系统内共有120个服务区，每个服务区通常由不同的运营主体管理。如果您需要了解特定区域或路段的服务区经营方信息，我可以协助生成数据报告，并通过筛选字段（如路段归属、运营模式等）进行深度分析。需要的话随时告诉我哦！ 🚘",
                        "message_id": "4870eca8-7594-414d-bd4f-f767c0b266ba",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_chat",
                                "format_response"
                            ],
                            "sql": null,
                            "type": "CHAT"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:52:24.296335"
                    },
                    {
                        "content": "当前数据库中能查到几个管理公司？",
                        "message_id": "2658b787-627f-4554-bd03-f76751149593",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:53:44.835966"
                    },
                    {
                        "content": "关于当前数据库中记录的管理公司数量，基于已有数据可作如下分析：\n\n1. **服务区关联数据**  \n系统内记录的120个高速公路服务区，每个服务区通常对应**独立的管理主体**（如物业公司、运营公司等），因此管理公司数量级约为**120家左右**。\n\n2. **潜在重叠情况**  \n若存在区域集中管理模式（如某公司同时管理多个相邻服务区），实际管理公司数量可能略低于120家。但因数据库未明确标注此类关联关系，建议通过以下方式获取精准数据：\n   - 指定路段或区域筛选\n   - 按管理类型（如自营/外包）过滤\n   - 关联企业资质信息查询\n\n需要我为您生成详细的管理公司清单或分析报告吗？可以随时补充筛选条件哦！ 📊",
                        "message_id": "0620aa40-a303-47ce-9e4a-45f18c173efe",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_chat",
                                "format_response"
                            ],
                            "sql": null,
                            "type": "CHAT"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:54:00.107883"
                    },
                    {
                        "content": "当前数据库高速公路服务区有几个管理公司？",
                        "message_id": "7f093649-94b0-4d66-bd47-ce3b574f5bbe",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T18:54:22.357083"
                    },
                    {
                        "content": "当前数据库高速公路服务区共有8个管理公司。",
                        "message_id": "43aa43b6-87e2-4410-8146-4555b87904b3",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT COUNT(*) AS 管理公司总数 \nFROM bss_company \nWHERE delete_ts IS NULL \nAND EXISTS (\n    SELECT 1 \n    FROM bss_service_area \n    WHERE bss_service_area.company_id = bss_company.id \n    AND delete_ts IS NULL\n);",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T18:54:50.006982"
                    },
                    {
                        "content": "当前数据库高速公路服务区有几个管理公司？",
                        "message_id": "a4b60280-769d-44b0-9ebc-d251d4a9315b",
                        "metadata": {},
                        "role": "user",
                        "timestamp": "2025-06-22T19:13:24.054588"
                    },
                    {
                        "content": "当前数据库中高速公路服务区的管理公司数量为8个。",
                        "message_id": "e5cf5b22-f9e2-45c2-80e9-7e4d223cad86",
                        "metadata": {
                            "execution_path": [
                                "start",
                                "classify",
                                "agent_database",
                                "format_response"
                            ],
                            "sql": "SELECT COUNT(DISTINCT c.id) AS company_count FROM bss_company c JOIN bss_service_area sa ON c.id = sa.company_id WHERE c.delete_ts IS NULL AND sa.delete_ts IS NULL;",
                            "type": "DATABASE"
                        },
                        "role": "assistant",
                        "timestamp": "2025-06-22T19:13:51.113852"
                    }
                ],
                "meta": {
                    "conversation_id": "conv_1750588941_6a14bbaa",
                    "created_at": "2025-06-22T18:42:21.008532",
                    "message_count": "17",
                    "updated_at": "2025-06-22T19:13:51.117862",
                    "user_id": "paul"
                },
                "updated_at": "2025-06-22T19:13:51.117862",
                "user_id": "paul"
            }
        ],
        "message_limit_applied": null,
        "query_time": "2025-06-22T22:39:29.100831",
        "response": "获取用户完整对话数据成功",
        "total_conversations": 4,
        "total_messages": 30,
        "user_id": "paul"
    },
    "message": "操作成功",
    "success": true
}
```

---

#### 获取对话系统统计

**接口信息**
- **URL**: `/api/v0/conversation_stats`
- **方法**: `GET`
- **功能**: 获取Redis对话系统的统计信息

**请求参数**
无

**请求示例**
```http
GET /api/v0/conversation_stats
```

**响应示例**
```json
{
    "code": 200,
    "data": {
        "available": true,
        "cached_qa_count": 3,
        "redis_info": {
            "connected_clients": 8,
            "memory_usage_mb": 1.37
        },
        "response": "获取统计信息成功",
        "total_conversations": 4,
        "total_users": 1
    },
    "message": "操作成功",
    "success": true
}
```

---

#### 清理过期对话

**接口信息**
- **URL**: `/api/v0/conversation_cleanup`
- **方法**: `POST`
- **功能**: 手动清理Redis中的过期对话数据

**请求参数**
无

**请求示例**
```http
POST /api/v0/conversation_cleanup
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "对话清理完成",
    "data": {}
}
```

---

### 问答缓存管理API

#### 获取问答缓存统计

**接口信息**
- **URL**: `/api/v0/qa_cache_stats`
- **方法**: `GET`
- **功能**: 获取问答缓存的详细统计信息

**请求参数**
无

**请求示例**
```http
GET /api/v0/qa_cache_stats
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取问答缓存统计成功",
    "data": {
        "available": true,
        "enabled": true,
        "total_count": 25,
        "memory_usage_mb": 2.5,
        "ttl_seconds": 86400,
        "ttl_hours": 24
    }
}
```

---

#### 获取问答缓存列表

**接口信息**
- **URL**: `/api/v0/qa_cache_list`
- **方法**: `GET`
- **功能**: 获取问答缓存列表，支持分页

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| limit | integer | 查询参数 | 否 | 50 | 限制返回记录数，最大500条 |

**请求示例**
```http
GET /api/v0/qa_cache_list?limit=100
```

**响应示例**
```json
{
    "code": 200,
    "data": {
        "cache_list": [
            {
                "cache_key": "qa_cache:3d99a761516672b1",
                "cached_at": "2025-06-22T20:30:10.964548",
                "has_sql": false,
                "has_summary": false,
                "question": "当前数据库高速公路管理公司最多管理几个服务区？",
                "response_type": "未知类型",
                "ttl_seconds": 79146
            },
            {
                "cache_key": "qa_cache:6410d614b026c745",
                "cached_at": "2025-06-22T19:59:01.711863",
                "has_sql": false,
                "has_summary": false,
                "question": "当前数据库高速公路服务区有几个管理公司？",
                "response_type": "未知类型",
                "ttl_seconds": 77274
            },
            {
                "cache_key": "qa_cache:7d674bc32386f20e",
                "cached_at": "2025-06-22T18:42:45.098209",
                "has_sql": false,
                "has_summary": false,
                "question": "请问河南的省会在哪里",
                "response_type": "未知类型",
                "ttl_seconds": 72699
            }
        ],
        "limit_applied": 50,
        "note": "按缓存时间倒序排列，最新的在前面",
        "response": "获取问答缓存列表成功",
        "total_returned": 3
    },
    "message": "操作成功",
    "success": true
}
```

---

#### 清空问答缓存

**接口信息**
- **URL**: `/api/v0/qa_cache_cleanup`
- **方法**: `POST`
- **功能**: 清空所有问答缓存

**请求参数**
无

**请求示例**
```http
POST /api/v0/qa_cache_cleanup
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "问答缓存清理完成",
    "data": {
        "deleted_count": 25,
        "cleared": true,
        "cleanup_time": "2024-12-22T15:30:00"
    }
}
```

---

### Embedding向量缓存管理API

#### 获取Embedding缓存统计

**接口信息**
- **URL**: `/api/v0/embedding_cache_stats`
- **方法**: `GET`
- **功能**: 获取embedding缓存统计信息

**请求参数**
无

**请求示例**
```http
GET /api/v0/embedding_cache_stats
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取embedding缓存统计成功",
    "data": {
        "enabled": true,
        "available": true,
        "total_count": 1250,
        "memory_usage_mb": 15.8
    }
}
```

---

#### 清空Embedding缓存

**接口信息**
- **URL**: `/api/v0/embedding_cache_cleanup`
- **方法**: `POST`
- **功能**: 清空所有embedding缓存

**请求参数**
无

**请求示例**
```http
POST /api/v0/embedding_cache_cleanup
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "所有embedding缓存已清空",
    "data": {
        "cleared": true
    }
}
```

---

### 智能问答API（使用Redis缓存）

#### 智能问答（支持对话上下文）

**接口信息**
- **URL**: `/api/v0/ask_agent`
- **方法**: `POST`
- **功能**: 支持对话上下文的智能问答接口，集成Redis对话管理和问答缓存

**请求参数**
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| question | string | 请求体 | 是 | - | 用户问题 |
| session_id | string | 请求体 | 否 | - | 浏览器会话ID |
| user_id | string | 请求体 | 否 | - | 用户ID |
| conversation_id | string | 请求体 | 否 | - | 对话ID |
| continue_conversation | boolean | 请求体 | 否 | false | 是否继续现有对话 |
| routing_mode | string | 请求体 | 否 | 配置文件 | 路由模式：database_direct/chat_direct/hybrid/llm_only |

**请求示例**
```http
POST /api/v0/ask_agent
Content-Type: application/json

{
    "question": "查询最近一个月的销售数据",
    "session_id": "session_12345",
    "user_id": "john_doe",
    "continue_conversation": true,
    "routing_mode": "hybrid"
}
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "查询执行完成",
    "data": {
        "type": "DATABASE",
        "response": "",
        "sql": "SELECT * FROM sales WHERE date >= DATE_SUB(NOW(), INTERVAL 1 MONTH)",
        "query_result": {
            "rows": [...],
            "columns": ["date", "amount", "product"],
            "row_count": 150,
            "total_row_count": 150,
            "is_limited": false
        },
        "summary": "查询到最近一个月的销售数据共150条记录...",
        "session_id": "session_12345",
        "execution_path": ["classify_question", "generate_sql", "execute_sql", "generate_summary"],
        "classification_info": {
            "question_type": "DATABASE",
            "confidence": 0.95,
            "method": "rule_based_database_keywords"
        },
        "conversation_id": "conv_1703145600_abc123",
        "user_id": "john_doe",
        "is_guest_user": false,
        "context_used": true,
        "from_cache": false,
        "conversation_status": "continued",
        "conversation_message": "继续现有对话"
    }
}
```

**缓存机制说明**
- **缓存存储**: 只有无上下文的问答会被缓存
- **缓存使用**: 无论是否有上下文都可以查找缓存
- **缓存优势**: 提高响应速度，减少重复计算

---

### 综合缓存管理API

#### 获取综合缓存概览

**接口信息**
- **URL**: `/api/v0/cache_overview_full`
- **方法**: `GET`
- **功能**: 获取所有缓存系统的综合概览

**请求参数**
无

**请求示例**
```http
GET /api/v0/cache_overview_full
```

**响应示例**
```json
{
    "success": true,
    "code": 200,
    "message": "获取综合缓存概览成功",
    "data": {
        "conversation_aware_cache": {
            "enabled": true,
            "total_items": 15,
            "sessions": ["session_12345", "session_67890"]
        },
        "question_answer_cache": {
            "available": true,
            "enabled": true,
            "total_count": 25,
            "memory_usage_mb": 2.5,
            "ttl_seconds": 86400,
            "ttl_hours": 24
        },
        "embedding_cache": {
            "enabled": true,
            "available": true,
            "total_count": 1250,
            "memory_usage_mb": 15.8
        },
        "redis_conversation_stats": {
            "available": true,
            "total_users": 125,
            "total_conversations": 1250,
            "cached_qa_count": 25,
            "redis_info": {
                "used_memory": "120MB",
                "connected_clients": 3
            }
        }
    }
}
```

---

## 错误处理

所有API都遵循统一的错误响应格式：

```json
{
    "success": false,
    "code": 500,
    "message": "处理失败",
    "data": {
        "error": "具体错误信息",
        "can_retry": true,
        "timestamp": "2024-12-22T15:30:00"
    }
}
```

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 422 | 参数验证失败 |
| 500 | 系统内部错误 |
| 503 | 服务暂时不可用（Redis连接失败等） |

---

## 配置参数

相关配置参数在 `app_config.py` 中定义：

```python
# Redis连接配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None

# 对话管理配置
CONVERSATION_CONTEXT_COUNT = 2          # 传递给LLM的上下文消息条数
CONVERSATION_MAX_LENGTH = 20            # 单个对话最大消息数
USER_MAX_CONVERSATIONS = 5              # 用户最大对话数
DEFAULT_ANONYMOUS_USER = "guest"        # 匿名用户统一ID

# 缓存开关配置
ENABLE_CONVERSATION_CONTEXT = True      # 是否启用对话上下文
ENABLE_QUESTION_ANSWER_CACHE = True     # 是否启用问答结果缓存
ENABLE_EMBEDDING_CACHE = True           # 是否启用embedding向量缓存

# TTL配置（单位：秒）
CONVERSATION_TTL = 7 * 24 * 3600        # 对话保存7天
USER_CONVERSATIONS_TTL = 7 * 24 * 3600  # 用户对话列表保存7天
QUESTION_ANSWER_TTL = 24 * 3600         # 问答结果缓存24小时
EMBEDDING_CACHE_TTL = 30 * 24 * 3600    # embedding向量缓存30天

# Embedding缓存管理配置
EMBEDDING_CACHE_MAX_SIZE = 5000         # 最大缓存问题数量
```

---

## 使用建议

### 1. 性能优化
- 合理使用分页参数控制返回数据量
- 使用缓存机制减少重复查询
- 定期清理过期数据

### 2. 安全考虑
- 验证用户权限和会话有效性
- 避免暴露敏感的对话内容
- 实施适当的访问频率限制

### 3. 最佳实践
- 使用 `/conversations/full` API 获取完整数据
- 根据业务需求设置合理的上下文长度
- 监控Redis内存使用情况
- 定期使用统计API监控系统状态

### 4. 缓存策略
- **问答缓存**: 严控存储条件（只缓存无上下文问答），放宽使用条件（提高命中率）
- **Embedding缓存**: 自动清理机制，避免内存溢出
- **对话缓存**: 基于TTL的自动过期，手动清理补充

---

## 更新日志

### v1.3.0 (2024-12-22)
- 🆕 新增问答缓存管理API：统计、列表、清理
- ✨ 问答缓存列表支持分页功能
- 🔧 优化综合缓存概览API，包含问答缓存统计
- 📝 完善API文档和使用说明

### v1.2.1 (2024-12-22)
- 🚀 平衡缓存策略：严控存储条件，放宽使用条件
- ⚡ 性能提升：多轮对话中的重复问题也能使用缓存
- 🎯 智能平衡：既保证缓存质量，又最大化利用率

### v1.2.0 (2024-12-22)
- 🔧 优化缓存策略：只缓存无上下文的问答，避免上下文污染
- ✨ 简化缓存键：基于问题本身生成缓存键，提高缓存命中率
- 🎯 逻辑优化：解决同一对话中重复问题无法使用缓存的问题

### v1.1.0 (2024-12-01)
- 🆕 新增用户完整对话数据API
- ✨ 支持一次性获取用户完整对话数据
- 🔧 优化参数处理，支持不传递限制参数时返回所有记录

### v1.0.0 (2024-11-01)
- 🎉 首次发布Redis缓存管理功能
- 📝 完整的API文档和使用指南 