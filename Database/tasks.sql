create extension if not exists pgcrypto;

create table if not exists public.extracted_tasks (
    id uuid primary key default gen_random_uuid(),
    
    title text not null,
    type text not null default 'class'
        check (type in ('class', 'assignment', 'announcement', 'event')),
    course text default null,
    description text default null,
    
    target_audience_year text default null,
    target_audience_program text default null,
    target_audience_faculty text default null,
    target_audience_other text default null,
    
    location_room text default null,
    location_campus text default null,
    location_detail text default null,
    
    registration_start timestamptz default null,
    registration_end timestamptz default null,
    
    start_at timestamptz default null,
    start_weekly_day text default null
        check (start_weekly_day in ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')),
    start_weekly_time time without time zone default null,
    
    end_at timestamptz default null,
    end_weekly_day text default null
        check (end_weekly_day in ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')),
    end_weekly_time time without time zone default null,
    
    deadline timestamptz default null,
    training_points integer default null,
    training_point_category text default null
        check (training_point_category in (
            'articles 1', 'articles 2', 'articles 3', 'articles 4', 'articles 5'
        )),
    estimated_hours double precision default null,
    
    source_url text not null,
    source_platform text not null default 'Portal'
        check (source_platform in (
            'Portal',
            'Moodle',
            'Khoa Công nghệ thôn tin',
            'Trường đại học Khoa học tự nhiên',
            'Phòng Công tác sinh viên',
            'VNUHMCUS',
            'Đoàn trường Khoa học tự nhiên',
            'Đoàn khoa - Liên chi hội khoa Môi trường',
            'Đoàn khoa - Liên chi hội khoa Hóa học',
            'Đoàn khoa - Liên chi hội khoa Sinh học',
            'Đoàn khoa - Liên chi hội khoa Địa chất',
            'Đoàn khoa - Liên chi hội khoa Vật lý',
            'Facebook Khoa Công nghệ thôn tin'
        )),
        
        updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    
    check (
        (start_at is null and start_weekly_day is null and start_weekly_time is null)
        or (start_at is not null and start_weekly_day is null and start_weekly_time is null)
        or (start_at is null and start_weekly_day is not null and start_weekly_time is not null)
    ),
    check (
        (end_at is null and end_weekly_day is null and end_weekly_time is null)
        or (end_at is not null and end_weekly_day is null and end_weekly_time is null)
        or (end_at is null and end_weekly_day is not null and end_weekly_time is not null)
    )
);

create index if not exists extracted_tasks_type_idx
    on public.extracted_tasks (type);

create index if not exists extracted_tasks_deadline_idx
    on public.extracted_tasks (deadline);

create index if not exists extracted_tasks_source_platform_idx
    on public.extracted_tasks (source_platform);
