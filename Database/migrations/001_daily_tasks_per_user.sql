BEGIN;

CREATE TEMP TABLE daily_tasks_legacy_data ON COMMIT DROP AS
SELECT work_date, task_id, is_completed_today
FROM daily_tasks;

DROP TABLE daily_tasks;

CREATE TABLE daily_tasks (
    user_id INT NOT NULL,
    work_date DATE NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    is_completed_today BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, work_date, task_id),
    FOREIGN KEY (user_id, task_id)
        REFERENCES user_tasks(user_id, task_id)
        ON DELETE CASCADE
);

INSERT INTO daily_tasks (user_id, work_date, task_id, is_completed_today)
SELECT user_tasks.user_id,
       daily_tasks_legacy_data.work_date,
       daily_tasks_legacy_data.task_id,
       daily_tasks_legacy_data.is_completed_today
FROM daily_tasks_legacy_data
JOIN user_tasks ON user_tasks.task_id = daily_tasks_legacy_data.task_id;

COMMIT;
