-- PostgreSQL schema. Connection settings are configured through .env.
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(64) PRIMARY KEY CHECK (btrim(id) <> ''),
    title VARCHAR(255) NOT NULL,
    type VARCHAR(30) NOT NULL,
    course_code VARCHAR(20),
    description TEXT,
    target_audience VARCHAR(100),
    location VARCHAR(100),
    registration_start TIMESTAMPTZ,
    registration_end TIMESTAMPTZ,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    deadline TIMESTAMPTZ,
    estimated_hours FLOAT,
    training_points INT NOT NULL DEFAULT 0,
    drl_category VARCHAR(20),
    recurrence VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    source_url TEXT,
    source_platform VARCHAR(50) NOT NULL DEFAULT 'custom',
    embedding TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tasks_title_length CHECK (
        char_length(title) BETWEEN 2 AND 255 AND btrim(title) <> ''
    ),
    CONSTRAINT tasks_type_valid CHECK (
        type IN ('class', 'assignment', 'exam', 'event', 'personal', 'tuition')
    ),
    CONSTRAINT tasks_course_code_valid CHECK (
        course_code IS NULL OR course_code ~ '^[A-Z]{3}[0-9]{5}$'
    ),
    CONSTRAINT tasks_registration_range CHECK (
        registration_start IS NULL
        OR registration_end IS NULL
        OR registration_start < registration_end
    ),
    CONSTRAINT tasks_time_range CHECK (
        start_time IS NULL OR end_time IS NULL OR start_time < end_time
    ),
    CONSTRAINT tasks_deadline_required CHECK (
        type NOT IN ('assignment', 'tuition') OR deadline IS NOT NULL
    ),
    CONSTRAINT tasks_estimated_hours_valid CHECK (
        estimated_hours IS NULL OR estimated_hours BETWEEN 0.25 AND 40.0
    ),
    CONSTRAINT tasks_training_points_valid CHECK (
        training_points BETWEEN 0 AND 100
    ),
    CONSTRAINT tasks_drl_category_valid CHECK (
        drl_category IS NULL
        OR drl_category IN ('dieu_1', 'dieu_2', 'dieu_3', 'dieu_4', 'dieu_5')
    ),
    CONSTRAINT tasks_drl_points_category CHECK (
        training_points = 0 OR drl_category IS NOT NULL
    ),
    CONSTRAINT tasks_status_valid CHECK (
        status IN ('active', 'done', 'archived', 'cancelled')
    ),
    CONSTRAINT tasks_source_platform_valid CHECK (
        source_platform IN ('moodle', 'portal', 'facebook', 'custom')
    )
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL CHECK (btrim(username) <> ''),
    email VARCHAR(100) UNIQUE NOT NULL CHECK (
        email ~ '^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$'
    ),
    full_name VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS user_tasks (
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id VARCHAR(64) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, task_id)
);

CREATE TABLE IF NOT EXISTS daily_tasks (
    user_id INT NOT NULL,
    work_date DATE NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    is_completed_today BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, work_date, task_id),
    FOREIGN KEY (user_id, task_id)
        REFERENCES user_tasks(user_id, task_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_deadline
    ON tasks(deadline) WHERE deadline IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_course
    ON tasks(course_code) WHERE course_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_status_type ON tasks(status, type);