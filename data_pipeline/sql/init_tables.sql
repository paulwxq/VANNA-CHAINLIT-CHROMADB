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
    id VARCHAR(32) PRIMARY KEY,                    -- 'task_20250627_143052'
    
    -- 任务基本信息
    task_type VARCHAR(50) NOT NULL DEFAULT 'data_workflow',
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/in_progress/partial_completed/completed/failed
    
    -- 配置和结果（JSON格式）
    parameters JSONB NOT NULL,                     -- 任务配置参数
    result JSONB,                                  -- 最终执行结果
    
    -- 错误处理
    error_message TEXT,                            -- 错误详细信息
    
    -- 步骤状态跟踪
    step_status JSONB DEFAULT '{
        "ddl_generation": "pending",
        "qa_generation": "pending", 
        "sql_validation": "pending",
        "training_load": "pending"
    }'::jsonb,
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- 创建者信息
    created_by VARCHAR(50) DEFAULT 'api',          -- 'api', 'manual', 'system'
    
    -- 输出目录
    output_directory TEXT,                         -- 任务输出目录路径
    
    -- 索引字段
    db_name VARCHAR(100),                          -- 数据库名称（便于筛选）
    business_context TEXT                          -- 业务上下文（便于搜索）
);

-- 添加约束
ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_task_status 
    CHECK (status IN ('pending', 'in_progress', 'partial_completed', 'completed', 'failed'));

ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_task_type 
    CHECK (task_type IN ('data_workflow', 'complete_workflow'));

ALTER TABLE data_pipeline_tasks ADD CONSTRAINT chk_created_by 
    CHECK (created_by IN ('api', 'manual', 'system'));

-- ====================================================================
-- 任务执行记录表 (data_pipeline_task_executions)
-- ====================================================================
CREATE TABLE IF NOT EXISTS data_pipeline_task_executions (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_step VARCHAR(50) NOT NULL,          -- 'ddl_generation', 'qa_generation', 'sql_validation', 'training_load', 'complete'
    status VARCHAR(20) NOT NULL,                  -- 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    execution_result JSONB,                       -- 步骤执行结果
    execution_id VARCHAR(100) UNIQUE,             -- {task_id}_step_{step_name}_exec_{timestamp}
    force_executed BOOLEAN DEFAULT FALSE,         -- 是否强制执行
    files_cleaned BOOLEAN DEFAULT FALSE,          -- 是否清理了旧文件
    duration_seconds INTEGER                      -- 执行时长（秒）
);

-- 添加约束
ALTER TABLE data_pipeline_task_executions ADD CONSTRAINT chk_execution_status 
    CHECK (status IN ('running', 'completed', 'failed'));

ALTER TABLE data_pipeline_task_executions ADD CONSTRAINT chk_execution_step 
    CHECK (execution_step IN ('ddl_generation', 'qa_generation', 'sql_validation', 'training_load', 'complete'));

ALTER TABLE data_pipeline_task_executions ADD CONSTRAINT chk_duration_positive 
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0);

-- ====================================================================
-- 任务日志表 (data_pipeline_task_logs)
-- ====================================================================
CREATE TABLE IF NOT EXISTS data_pipeline_task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id) ON DELETE SET NULL,
    
    -- 日志内容
    log_level VARCHAR(10) NOT NULL,               -- 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,                        -- 日志消息内容
    
    -- 上下文信息
    step_name VARCHAR(50),                        -- 执行步骤名称
    module_name VARCHAR(100),                     -- 模块名称
    function_name VARCHAR(100),                   -- 函数名称
    
    -- 时间戳
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 额外信息（JSON格式）
    extra_data JSONB DEFAULT '{}'::jsonb          -- 额外的结构化信息
);

-- 添加约束
ALTER TABLE data_pipeline_task_logs ADD CONSTRAINT chk_log_level 
    CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'));

-- ====================================================================
-- 任务输出文件表 (data_pipeline_task_outputs)
-- ====================================================================
CREATE TABLE IF NOT EXISTS data_pipeline_task_outputs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id) ON DELETE SET NULL,
    
    -- 文件信息
    file_type VARCHAR(50) NOT NULL,               -- 'ddl', 'md', 'json', 'log', 'report'
    file_name VARCHAR(255) NOT NULL,              -- 文件名
    file_path TEXT NOT NULL,                      -- 相对路径
    file_size BIGINT DEFAULT 0,                   -- 文件大小（字节）
    
    -- 文件内容摘要
    content_hash VARCHAR(64),                     -- 文件内容hash
    description TEXT,                             -- 文件描述
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 状态
    is_primary BOOLEAN DEFAULT FALSE,             -- 是否为主要输出文件
    is_downloadable BOOLEAN DEFAULT TRUE          -- 是否可下载
);

-- 添加约束
ALTER TABLE data_pipeline_task_outputs ADD CONSTRAINT chk_file_type 
    CHECK (file_type IN ('ddl', 'md', 'json', 'log', 'report', 'txt', 'other'));

ALTER TABLE data_pipeline_task_outputs ADD CONSTRAINT chk_file_size_positive 
    CHECK (file_size >= 0);

-- ====================================================================
-- 创建索引
-- ====================================================================

-- 任务表索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON data_pipeline_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_db_name ON data_pipeline_tasks(db_name);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON data_pipeline_tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_tasks_task_type ON data_pipeline_tasks(task_type);

-- 执行记录表索引
CREATE INDEX IF NOT EXISTS idx_executions_task_id ON data_pipeline_task_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_executions_step ON data_pipeline_task_executions(execution_step);
CREATE INDEX IF NOT EXISTS idx_executions_status ON data_pipeline_task_executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_started_at ON data_pipeline_task_executions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_executions_task_step ON data_pipeline_task_executions(task_id, execution_step);

-- 日志表索引
CREATE INDEX IF NOT EXISTS idx_logs_task_id ON data_pipeline_task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_execution_id ON data_pipeline_task_logs(execution_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON data_pipeline_task_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON data_pipeline_task_logs(log_level);
CREATE INDEX IF NOT EXISTS idx_logs_step ON data_pipeline_task_logs(step_name);
CREATE INDEX IF NOT EXISTS idx_logs_task_timestamp ON data_pipeline_task_logs(task_id, timestamp DESC);

-- 文件输出表索引
CREATE INDEX IF NOT EXISTS idx_outputs_task_id ON data_pipeline_task_outputs(task_id);
CREATE INDEX IF NOT EXISTS idx_outputs_execution_id ON data_pipeline_task_outputs(execution_id);
CREATE INDEX IF NOT EXISTS idx_outputs_file_type ON data_pipeline_task_outputs(file_type);
CREATE INDEX IF NOT EXISTS idx_outputs_primary ON data_pipeline_task_outputs(is_primary) WHERE is_primary = TRUE;
CREATE INDEX IF NOT EXISTS idx_outputs_downloadable ON data_pipeline_task_outputs(is_downloadable) WHERE is_downloadable = TRUE;

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
    
    -- 删除旧任务（级联删除相关日志和文件记录）
    DELETE FROM data_pipeline_tasks 
    WHERE created_at < cutoff_date 
    AND status IN ('completed', 'failed');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    -- 记录清理操作
    INSERT INTO data_pipeline_task_logs (task_id, log_level, message, step_name)
    VALUES ('system', 'INFO', 
            FORMAT('清理了 %s 个超过 %s 天的旧任务', deleted_count, days_to_keep),
            'cleanup');
    
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
    
    -- 查找超时的运行中执行
    UPDATE data_pipeline_task_executions 
    SET status = 'failed',
        error_message = FORMAT('执行超时（超过%s小时），可能已停止运行', timeout_hours),
        completed_at = NOW()
    WHERE status = 'running' 
    AND started_at < cutoff_time;
    
    GET DIAGNOSTICS zombie_count = ROW_COUNT;
    
    -- 更新相关任务状态
    UPDATE data_pipeline_tasks 
    SET status = 'failed',
        error_message = FORMAT('任务超时（超过%s小时），可能已停止运行', timeout_hours)
    WHERE status IN ('in_progress') 
    AND started_at < cutoff_time;
    
    -- 记录检查操作
    IF zombie_count > 0 THEN
        INSERT INTO data_pipeline_task_logs (task_id, log_level, message, step_name)
        VALUES ('system', 'WARNING', 
                FORMAT('发现并处理了 %s 个僵尸执行', zombie_count),
                'zombie_check');
    END IF;
    
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

-- 任务执行概览视图
CREATE OR REPLACE VIEW v_task_execution_overview AS
SELECT 
    t.id as task_id,
    t.task_type,
    t.status as task_status,
    t.step_status,
    t.created_at,
    t.started_at,
    t.completed_at,
    t.created_by,
    t.db_name,
    COALESCE(e.current_execution, '{}') as current_execution,
    COALESCE(e.execution_count, 0) as total_executions
FROM data_pipeline_tasks t
LEFT JOIN (
    SELECT 
        task_id,
        COUNT(*) as execution_count,
        json_build_object(
            'execution_id', e1.execution_id,
            'step', e1.execution_step,
            'status', e1.status,
            'started_at', e1.started_at
        ) as current_execution
    FROM data_pipeline_task_executions e1
    WHERE e1.id = (
        SELECT e2.id 
        FROM data_pipeline_task_executions e2 
        WHERE e2.task_id = e1.task_id 
        ORDER BY e2.started_at DESC 
        LIMIT 1
    )
    GROUP BY task_id, e1.execution_id, e1.execution_step, e1.status, e1.started_at
) e ON t.id = e.task_id;

-- 提交事务
COMMIT;

-- 输出创建结果
\echo 'Data Pipeline API 数据库表创建完成！'
\echo ''
\echo '已创建的表：'
\echo '- data_pipeline_tasks: 任务主表'
\echo '- data_pipeline_task_executions: 任务执行记录表'
\echo '- data_pipeline_task_logs: 任务日志表'
\echo '- data_pipeline_task_outputs: 任务输出文件表'
\echo ''
\echo '已创建的函数：'
\echo '- cleanup_old_data_pipeline_tasks(days): 清理旧任务'
\echo '- get_data_pipeline_task_stats(): 获取任务统计'
\echo '- check_zombie_data_pipeline_tasks(hours): 检查僵尸任务'
\echo ''
\echo '已创建的视图：'
\echo '- v_task_execution_overview: 任务执行概览'