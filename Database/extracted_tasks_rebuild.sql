-- Rebuild public.extracted_tasks to match Backend/Regulation/ExtractedTask.py.
-- This drops the existing table and its data. Export the table first if the
-- current data needs to be preserved.

begin;

drop table if exists public.extracted_tasks;

create extension if not exists pgcrypto;

create table public.extracted_tasks (
    id uuid primary key default gen_random_uuid(),

    title text not null,
    type text not null
        check (type in ('class', 'assignment', 'announcement', 'event')),
    
    source_platform text not null
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
    
    course text,
    description text,

    target_audience_year text
        check (target_audience_year is null or target_audience_year in ('1', '2', '3', '4')),
    target_audience_program text
        check (target_audience_program is null or target_audience_program in (
            'Đại trà (chuẩn)',
            'Đề án',
            'Tăng cường tiếng Anh (chất lượng cao)',
            'Tiên tiến / Liên kết quốc tế',
            'Cử nhân tài năng',
            'Đại học chính quy',
            'Sau đại học'
        )),
    target_audience_faculty text
        check (target_audience_faculty is null or target_audience_faculty in (
            'Toán - Tin học',
            'Công nghệ Thông tin',
            'Vật lý - Vật lý Kỹ thuật',
            'Hóa học',
            'Sinh học - Công nghệ Sinh học',
            'Điện tử - Viễn thông',
            'Khoa học và Công nghệ Vật liệu',
            'Môi trường',
            'Địa chất',
            'Khoa học Liên ngành'
        )),
    target_audience_other text,

    location_room text,
    location_campus text
        check (location_campus is null or location_campus in (
            'Nguyễn Văn Cừ (cơ sở 1)',
            'Thủ Đức (cơ sở 2)'
        )),
    location_detail text,

    registration_start timestamptz,
    registration_end timestamptz,

    start_at timestamptz,
    start_weekly_day text
        check (start_weekly_day is null or start_weekly_day in ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')),
    start_weekly_time time without time zone,

    end_at timestamptz,
    end_weekly_day text
        check (end_weekly_day is null or end_weekly_day in ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')),
    end_weekly_time time without time zone,

    deadline timestamptz,
    training_points integer
        check (
            training_points is null
            or type <> 'event'
            or training_points between 0 and 24
        ),
    training_point_category text
        check (training_point_category is null or training_point_category in (
            'Articles 1',
            'Articles 2',
            'Articles 3',
            'Articles 4',
            'Articles 5'
        )),
    estimated_hours double precision
        check (
            estimated_hours is null
            or type not in ('event', 'assignment')
            or estimated_hours > 0
        ),
    
    source_url text not null,
    updated_at timestamptz not null default now(),

    check (
        (start_at is null and start_weekly_day is null and start_weekly_time is null)
        or (start_at is not null and start_weekly_day is null and start_weekly_time is null)
        or (start_at is null and start_weekly_day is not null and start_weekly_time is not null)
    ),
    check (
        (end_at is null and end_weekly_day is null and end_weekly_time is null)
        or (end_at is not null and end_weekly_day is null and end_weekly_time is null)
        or (end_at is null and end_weekly_day is not null and end_weekly_time is not null)
    ),
    check (
        type <> 'event'
        or (training_points is not null and training_point_category is not null)
    ),
    check (
        type not in ('event', 'assignment')
        or estimated_hours is not null
    )
);

create index extracted_tasks_type_idx
    on public.extracted_tasks (type);

create index extracted_tasks_deadline_idx
    on public.extracted_tasks (deadline);

create index extracted_tasks_source_platform_idx
    on public.extracted_tasks (source_platform);

commit;
