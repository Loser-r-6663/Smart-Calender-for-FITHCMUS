-- ==============================================================================
-- Bảng public.tasks: CHỈ LƯU TASK CHUNG (Public / Common tasks)
-- Các task riêng của từng người dùng được lưu ở bảng public.user_task
-- ==============================================================================

create table public.tasks (
  id uuid not null default gen_random_uuid (),
  title text not null,
  type text not null,
  course text null,
  description text null,
  target_audience_year text null,
  target_audience_program text null,
  target_audience_faculty text null,
  target_audience_other text null,
  location_room text null,
  location_campus text null,
  location_detail text null,
  registration_start timestamp with time zone null,
  registration_end timestamp with time zone null,
  start_at timestamp with time zone null,
  start_weekly_day text null,
  start_weekly_time time without time zone null,
  end_at timestamp with time zone null,
  end_weekly_day text null,
  end_weekly_time time without time zone null,
  deadline timestamp with time zone null,
  training_points integer null,
  training_point_category text null,
  estimated_hours double precision null,
  source_url text not null,
  source_platform text not null,
  updated_at timestamp with time zone not null default now(),
  constraint tasks_pkey primary key (id),
  constraint tasks_type_check check (
    type = any (
      array[
        'class'::text,
        'assignment'::text,
        'announcement'::text,
        'event'::text
      ]
    )
  ),
  constraint tasks_source_platform_check check (
    source_platform = any (
      array[
        'Portal'::text,
        'Moodle'::text,
        'Khoa Công nghệ thông tin'::text,
        'Trường đại học Khoa học tự nhiên'::text,
        'Phòng Công tác sinh viên'::text,
        'VNUHCMUS'::text,
        'Đoàn trường Khoa học tự nhiên'::text,
        'Đoàn khoa - Liên chi hội khoa Môi trường'::text,
        'Đoàn khoa - Liên chi hội khoa Hóa học'::text,
        'Đoàn khoa - Liên chi hội khoa Sinh học'::text,
        'Đoàn khoa - Liên chi hội khoa Địa chất'::text,
        'Đoàn khoa - Liên chi hội khoa Vật lý'::text,
        'Facebook Khoa Công nghệ thông tin'::text
      ]
    )
  ),
  constraint tasks_target_audience_year_check check (
    target_audience_year is null
    or target_audience_year = any (array['1'::text, '2'::text, '3'::text, '4'::text])
  ),
  constraint tasks_target_audience_program_check check (
    target_audience_program is null
    or target_audience_program = any (
      array[
        'Đại trà (chuẩn)'::text,
        'Đề án'::text,
        'Tăng cường tiếng Anh (chất lượng cao)'::text,
        'Tiên tiến / Liên kết quốc tế'::text,
        'Cử nhân tài năng'::text,
        'Đại học chính quy'::text,
        'Sau đại học'::text
      ]
    )
  ),
  constraint tasks_target_audience_faculty_check check (
    target_audience_faculty is null
    or target_audience_faculty = any (
      array[
        'Toán - Tin học'::text,
        'Công nghệ Thông tin'::text,
        'Vật lý - Vật lý Kỹ thuật'::text,
        'Hóa học'::text,
        'Sinh học - Công nghệ Sinh học'::text,
        'Điện tử - Viễn thông'::text,
        'Khoa học và Công nghệ Vật liệu'::text,
        'Môi trường'::text,
        'Địa chất'::text,
        'Khoa học Liên ngành'::text
      ]
    )
  ),
  constraint tasks_location_campus_check check (
    location_campus is null
    or location_campus = any (
      array[
        'Nguyễn Văn Cừ (cơ sở 1)'::text,
        'Thủ Đức (cơ sở 2)'::text
      ]
    )
  ),
  constraint tasks_start_weekly_day_check check (
    start_weekly_day is null
    or start_weekly_day = any (
      array['T2'::text, 'T3'::text, 'T4'::text, 'T5'::text, 'T6'::text, 'T7'::text, 'CN'::text]
    )
  ),
  constraint tasks_end_weekly_day_check check (
    end_weekly_day is null
    or end_weekly_day = any (
      array['T2'::text, 'T3'::text, 'T4'::text, 'T5'::text, 'T6'::text, 'T7'::text, 'CN'::text]
    )
  ),
  constraint tasks_training_point_category_check check (
    training_point_category is null
    or training_point_category = any (
      array[
        'Articles 1'::text,
        'Articles 2'::text,
        'Articles 3'::text,
        'Articles 4'::text,
        'Articles 5'::text
      ]
    )
  ),
  constraint tasks_training_points_check check (
    type <> 'event'::text
    or (
      training_points is not null
      and training_points >= 0
      and training_points < 25
    )
  ),
  constraint tasks_event_training_point_category_check check (
    type <> 'event'::text
    or (
      training_points = 0
      and training_point_category is null
    )
    or (
      training_points > 0
      and training_point_category is not null
    )
  ),
  constraint tasks_estimated_hours_check check (
    (
      type = any (array['class'::text, 'announcement'::text])
    )
    or (
      type = 'assignment'::text
      and (estimated_hours is null or estimated_hours > 0)
    )
    or (
      type = 'event'::text
      and estimated_hours is not null
      and estimated_hours > 0
    )
  ),
  constraint tasks_start_time_check check (
    (
      start_at is null
      and start_weekly_day is null
      and start_weekly_time is null
    )
    or (
      start_at is not null
      and start_weekly_day is null
      and start_weekly_time is null
    )
    or (
      start_at is null
      and start_weekly_day is not null
      and start_weekly_time is not null
    )
  ),
  constraint tasks_end_time_check check (
    (
      end_at is null
      and end_weekly_day is null
      and end_weekly_time is null
    )
    or (
      end_at is not null
      and end_weekly_day is null
      and end_weekly_time is null
    )
    or (
      end_at is null
      and end_weekly_day is not null
      and end_weekly_time is not null
    )
  )
) TABLESPACE pg_default;

create index if not exists tasks_type_idx on public.tasks using btree (type) tablespace pg_default;
create index if not exists tasks_deadline_idx on public.tasks using btree (deadline) tablespace pg_default;
create index if not exists tasks_source_platform_idx on public.tasks using btree (source_platform) tablespace pg_default;
