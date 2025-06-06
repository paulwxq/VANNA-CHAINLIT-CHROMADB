## 使用PgVector作为向量数据库

### 1.下面是langchain自动创建的表结构，可以参考这个结构来创建自己的表结构。

```sql
-- 创建向量表
create table public.langchain_pg_embedding
(
    id            varchar not null
        primary key,
    collection_id uuid
        references public.langchain_pg_collection
            on delete cascade,
    embedding     vector,
    document      varchar,
    cmetadata     jsonb
);

alter table public.langchain_pg_embedding
    owner to postgres;

create index ix_cmetadata_gin
    on public.langchain_pg_embedding using gin (cmetadata jsonb_path_ops);

-- 创建集合表
create table public.langchain_pg_collection
(
    uuid      uuid    not null
        primary key,
    name      varchar not null
        unique,
    cmetadata json
);

alter table public.langchain_pg_collection
    owner to postgres;


```

### 2. 为了便于测试，我会删除向量表的外键。

```sql  
alter table public.langchain_pg_embedding
    drop constraint langchain_pg_embedding_collection_id_fkey;
```







