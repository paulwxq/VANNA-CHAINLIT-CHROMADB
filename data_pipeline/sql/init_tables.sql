-- Data Pipeline API 数据库初始化脚本
-- 
-- 此脚本在pgvector向量数据库中创建Data Pipeline API系统所需的表和索引
-- 注意：这些表应该创建在pgvector数据库中，而不是业务数据库中
-- 
-- 执行方式（使用PGVECTOR_CONFIG中的连接信息）：
-- psql -h host -p port -U username -d pgvector_database_name -f init_tables.sql

-- 设置客户端编码
SET client_encoding = 'UTF8';

-- 开始事务
BEGIN;

-- ====================================================================
-- 任务主表 (data_pipeline_tasks)
-- ====================================================================
CREATE TABLE IF NOT EXISTS data_pipeline_tasks (
    -- 主键：时间戳格式的任务ID
    task_id VARCHAR(32) PRIMARY KEY,               -- 'task_20250627_143052'
    
    -- 任务基本信息
    task_type VARCHAR(50) NOT NULL DEFAULT 'data_workflow',
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/in_progress/partial_completed/completed/failed
    
    -- 配置和结果（JSON格式）
    parameters JSONB NOT NULL,                     -- 任务配置参数
    result JSONB,                                  -- 最终执行结果
    
    -- 错误处理
    error_message TEXT,                            -- 错误详细信息
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- 创建者信息
    created_type VARCHAR(50) DEFAULT 'api',        -- 'api', 'manual', 'system'
    by_user VARCHAR(50),                           -- 'guest'或其它user_id
    
    -- 输出目录
    output_directory TEXT,                         -- 任务输出目录路径
    
    -- 索引字段
    db_name VARCHAR(100)                           -- 数据库名称（便于筛选）
);

-- 添加约束
ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_task_status 
    CHECK (status IN ('pending', 'in_progress', 'partial_completed', 'completed', 'failed'));

ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_task_type 
    CHECK (task_type IN ('data_workflow', 'complete_workflow'));

ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_created_type 
    CHECK (created_type IN ('api', 'manual', 'system'));

-- ====================================================================
-- 任务步骤状态表 (data_pipeline_task_steps)
-- ====================================================================
CREATE TABLE IF NOT EXISTS data_pipeline_task_steps (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(task_id) ON DELETE CASCADE,
    execution_id VARCHAR(100),                    -- 执行批次ID（可为空）
    step_name VARCHAR(50) NOT NULL,               -- 'ddl_generation', 'qa_generation', 'sql_validation', 'training_load'
    step_status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT                            -- 错误详细信息
);

-- 添加约束
ALTER TABLE data_pipeline_task_steps ADD CONSTRAINT chk_step_status 
    CHECK (step_status IN ('pending', 'running', 'completed', 'failed'));

ALTER TABLE data_pipeline_task_steps ADD CONSTRAINT chk_step_name 
    CHECK (step_name IN ('ddl_generation', 'qa_generation', 'sql_validation', 'training_load'));



-- ====================================================================
-- 创建索引
-- ====================================================================

-- 任务表索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON data_pipeline_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_db_name ON data_pipeline_tasks(db_name);
CREATE INDEX IF NOT EXISTS idx_tasks_created_type ON data_pipeline_tasks(created_type);
CREATE INDEX IF NOT EXISTS idx_tasks_task_type ON data_pipeline_tasks(task_type);

-- 步骤状态表索引
CREATE INDEX IF NOT EXISTS idx_steps_task_id ON data_pipeline_task_steps(task_id);
CREATE INDEX IF NOT EXISTS idx_steps_step_name ON data_pipeline_task_steps(step_name);
CREATE INDEX IF NOT EXISTS idx_steps_step_status ON data_pipeline_task_steps(step_status);
CREATE INDEX IF NOT EXISTS idx_steps_started_at ON data_pipeline_task_steps(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_steps_task_step ON data_pipeline_task_steps(task_id, step_name);

-- ====================================================================
-- 创建清理函数
-- ====================================================================

-- 清理旧任务的函数
CREATE OR REPLACE FUNCTION cleanup_old_data_pipeline_tasks(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    cutoff_date TIMESTAMP;
BEGIN
    cutoff_date := NOW() - INTERVAL '1 day' * days_to_keep;
    
    -- 删除旧任务（级联删除相关步骤记录）
    DELETE FROM data_pipeline_tasks 
    WHERE created_at < cutoff_date 
    AND status IN ('completed', 'failed');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 获取任务统计信息的函数
CREATE OR REPLACE FUNCTION get_data_pipeline_task_stats()
RETURNS TABLE (
    total_tasks INTEGER,
    pending_tasks INTEGER,
    running_tasks INTEGER,
    completed_tasks INTEGER,
    failed_tasks INTEGER,
    avg_completion_time INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::INTEGER as total_tasks,
        COUNT(*) FILTER (WHERE status = 'pending')::INTEGER as pending_tasks,
        COUNT(*) FILTER (WHERE status IN ('in_progress'))::INTEGER as running_tasks,
        COUNT(*) FILTER (WHERE status = 'completed')::INTEGER as completed_tasks,
        COUNT(*) FILTER (WHERE status = 'failed')::INTEGER as failed_tasks,
        AVG(completed_at - started_at) FILTER (WHERE status = 'completed') as avg_completion_time
    FROM data_pipeline_tasks;
END;
$$ LANGUAGE plpgsql;

-- 检查僵尸任务的函数
CREATE OR REPLACE FUNCTION check_zombie_data_pipeline_tasks(timeout_hours INTEGER DEFAULT 2)
RETURNS INTEGER AS $$
DECLARE
    zombie_count INTEGER;
    cutoff_time TIMESTAMP;
BEGIN
    cutoff_time := NOW() - INTERVAL '1 hour' * timeout_hours;
    
    -- 查找超时的运行中步骤
    UPDATE data_pipeline_task_steps 
    SET step_status = 'failed',
        error_message = FORMAT('步骤执行超时（超过%s小时），可能已停止运行', timeout_hours),
        completed_at = NOW()
    WHERE step_status = 'running' 
    AND started_at < cutoff_time;
    
    GET DIAGNOSTICS zombie_count = ROW_COUNT;
    
    -- 更新相关任务状态
    UPDATE data_pipeline_tasks 
    SET status = 'failed',
        error_message = FORMAT('任务超时（超过%s小时），可能已停止运行', timeout_hours)
    WHERE status IN ('in_progress') 
    AND started_at < cutoff_time;
    
    RETURN zombie_count;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================
-- 插入初始数据（如果需要）
-- ====================================================================

-- 这里可以插入一些初始配置数据
-- 目前暂时不需要

-- ====================================================================
-- 创建视图（便于查询）
-- ====================================================================

-- 任务步骤概览视图
CREATE OR REPLACE VIEW v_task_step_overview AS
SELECT 
    t.task_id,
    t.task_type,
    t.status as task_status,
    t.created_at,
    t.started_at,
    t.completed_at,
    t.created_type,
    t.by_user,
    t.db_name,
    s.step_name,
    s.step_status,
    s.started_at as step_started_at,
    s.completed_at as step_completed_at,
    s.error_message as step_error_message
FROM data_pipeline_tasks t
LEFT JOIN data_pipeline_task_steps s ON t.task_id = s.task_id
ORDER BY t.created_at DESC, 
         CASE s.step_name 
           WHEN 'ddl_generation' THEN 1
           WHEN 'qa_generation' THEN 2
           WHEN 'sql_validation' THEN 3
           WHEN 'training_load' THEN 4
           ELSE 5 
         END;

-- 提交事务
COMMIT;

-- 输出创建结果
\echo 'Data Pipeline API 数据库表创建完成！'
\echo ''
\echo '已创建的表：'
\echo '- data_pipeline_tasks: 任务主表'
\echo '- data_pipeline_task_steps: 任务步骤状态表'
\echo ''
\echo '已创建的函数：'
\echo '- cleanup_old_data_pipeline_tasks(days): 清理旧任务'
\echo '- get_data_pipeline_task_stats(): 获取任务统计'
\echo '- check_zombie_data_pipeline_tasks(hours): 检查僵尸任务'
\echo ''
\echo '已创建的视图：'
\echo '- v_task_step_overview: 任务步骤概览'