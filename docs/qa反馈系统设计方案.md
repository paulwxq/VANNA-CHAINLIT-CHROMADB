# QA反馈系统集成指南 - 复用Vanna连接

需求：
请检查我在知识库的代码，我希望在citu_app.py添加一组API，实现下面的功能：
1.我会在app_db中创建一个表：
这个表用来存储用户给question和sql点赞的场景：
CREATE TABLE qa_feedback ( id SERIAL PRIMARY KEY, -- 主键，自增 question TEXT NOT NULL, -- 问题内容 sql TEXT NOT NULL, -- 生成的SQL is_thumb_up BOOLEAN NOT NULL, -- 是否点赞（true=点赞，false=点踩） user_id VARCHAR(64) NOT NULL, -- 用户ID create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间 is_in_training_data BOOLEAN DEFAULT FALSE, -- 是否已加入数据集 update_time TIMESTAMP -- 更新时间 );
2.围绕着表和添加训练数据集的功能，添加下面的API:
a.) 查询API(包括分页和排序)，在审核页面中，可以列出当前所有点赞的数据，我需要一个Post API，可以对点赞数据执行查询和分页，以及排序。

 包括 is_thumb_up，create_time 时间范围，is_in_training_data等等。
b.) 删除API，选定某个id，点击删除。
c.) 添加到训练数据集的API，只需要question:sql 两个字段，但是需要知道是正向，还是负向。
d.) 修改API，允许修改后提交，一个API，update某条记录。
请先理解我上面的需求，阅读citu_app.py，以及与它相关的代码，然后，再进行设计工作，在在进行设计时请注意：访问数据库，以及写入训练集数据，应该都有现成的function，你要尽量复用这些方法。另外写入数据集时，有两种数据，点赞的是写入SQL，点负面的是写入到error_sql.
请先不要写代码，先理解需求，了解限制，进行设计，然后与我讨论设计。


## 📁 文件结构

```
项目根目录/
├── common/
│   ├── qa_feedback_manager.py          # 新增：反馈数据管理器
│   └── ...其他common模块
├── citu_app.py                         # 修改：添加API端点
└── app_config.py                       # 无需修改（已有APP_DB_CONFIG）
```

## 🔧 连接管理优势

### ✅ 方案一特点：
- **智能连接复用**：优先使用现有vanna连接，降低资源占用
- **自动降级**：vanna连接不可用时自动创建新连接
- **零配置集成**：无需额外配置，与现有架构无缝兼容
- **性能优化**：减少数据库连接数，提高系统性能

### 📊 连接逻辑：
```
1. 尝试获取vanna实例 ✓
   ├─ 成功：复用vanna.engine
   └─ 失败：创建独立连接池
2. 测试连接有效性 ✓
3. 自动创建qa_feedback表 ✓
```

## 🚀 集成步骤

### 1. 放置反馈管理器文件
将 `qa_feedback_manager.py` 放在 `common/` 目录下。

### 2. 修改 citu_app.py

#### 2.1 添加导入语句
```python
# 在现有import后添加
from common.qa_feedback_manager import QAFeedbackManager
from common.result import success_response, bad_request_response, not_found_response, internal_error_response
```

#### 2.2 添加管理器初始化函数
```python
# 全局反馈管理器实例
qa_feedback_manager = None

def get_qa_feedback_manager():
    """获取QA反馈管理器实例（懒加载）- 复用Vanna连接版本"""
    global qa_feedback_manager
    if qa_feedback_manager is None:
        try:
            # 优先尝试复用vanna连接
            vanna_instance = None
            try:
                # 尝试获取现有的vanna实例
                if 'get_citu_langraph_agent' in globals():
                    agent = get_citu_langraph_agent()
                    if hasattr(agent, 'vn'):
                        vanna_instance = agent.vn
                elif 'vn' in globals():
                    vanna_instance = vn
                else:
                    print("[INFO] 未找到可用的vanna实例，将创建新的数据库连接")
            except Exception as e:
                print(f"[INFO] 获取vanna实例失败: {e}，将创建新的数据库连接")
                vanna_instance = None
            
            qa_feedback_manager = QAFeedbackManager(vanna_instance=vanna_instance)
            print("[CITU_APP] QA反馈管理器实例创建成功")
        except Exception as e:
            print(f"[CRITICAL] QA反馈管理器创建失败: {str(e)}")
            raise Exception(f"QA反馈管理器初始化失败: {str(e)}")
    return qa_feedback_manager
```

#### 2.3 添加所有API端点
将完整集成示例中的所有6个API函数复制到 `citu_app.py` 文件末尾。

## 🔧 API端点一览

| API端点 | 方法 | 功能 |
|---------|------|------|
| `/api/v0/qa_feedback/query` | POST | 查询反馈记录（分页、筛选、排序） |
| `/api/v0/qa_feedback/delete/{id}` | DELETE | 删除反馈记录 |
| `/api/v0/qa_feedback/update/{id}` | PUT | 修改反馈记录 |
| `/api/v0/qa_feedback/add_to_training` | POST | **核心功能**：批量添加到训练集 |
| `/api/v0/qa_feedback/add` | POST | 创建反馈记录 |
| `/api/v0/qa_feedback/stats` | GET | 统计信息 |

## 💡 核心功能：混合批量训练

```http
POST /api/v0/qa_feedback/add_to_training
Content-Type: application/json

{
  "feedback_ids": [1, 2, 3, 4, 5]
}
```

**自动分类处理：**
- ✅ `is_thumb_up=true` → `vn.train(question, sql)` （正向训练）
- ❌ `is_thumb_up=false` → `vn.train_error_sql(question, sql)` （负向训练）

## 🧪 验证安装

### 启动服务器后检查：
1. **连接复用日志**：
   ```
   [QAFeedbackManager] 复用Vanna数据库连接
   [QAFeedbackManager] qa_feedback表检查/创建成功
   ```

2. **测试API**：
   ```bash
   # 获取统计信息
   curl http://localhost:5000/api/v0/qa_feedback/stats
   
   # 应返回：
   {
     "success": true,
     "data": {
       "total_feedback": 0,
       "positive_feedback": 0,
       "negative_feedback": 0,
       ...
     }
   }
   ```

## ⚠️ 注意事项

1. **连接复用逻辑**：系统会自动尝试复用vanna连接，失败时自动创建新连接
2. **数据库权限**：确保APP_DB_CONFIG配置的用户有创建表和索引的权限
3. **训练集成**：需要确保vn实例已正确初始化，包含train()和train_error_sql()方法
4. **性能监控**：复用连接模式下，所有数据库操作共享连接池，请关注连接池状态

## 🎯 工作流程

1. **用户反馈** → 点赞/点踩生成反馈记录
2. **审核管理** → 使用查询API筛选待处理记录  
3. **批量训练** → 选择记录调用训练API
4. **状态跟踪** → 系统自动标记训练状态，避免重复训练

恭喜！现在你的QA反馈系统已经完成集成，可以开始使用了！🎉