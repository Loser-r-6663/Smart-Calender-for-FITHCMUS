begin;

alter table public.user_task
  drop constraint if exists user_task_source_platform_check,
  drop constraint if exists user_task_training_points_check,
  drop constraint if exists user_task_event_training_point_category_check,
  drop constraint if exists user_task_estimated_hours_check;

alter table public.user_task
  add constraint user_task_source_platform_check check (
    source_platform = any (
      array[
        'Portal'::text,
        'Moodle'::text,
        'Khoa Công nghệ thông tin'::text,
        'Trường đại học Khoa học tự nhiên'::text,
        'Phòng Công tác sinh viên'::text,
        'VNUHMCUS'::text,
        'VNUHCMUS'::text,
        'Đoàn trường Khoa học tự nhiên'::text,
        'Đoàn khoa - Liên chi hội khoa Môi trường'::text,
        'Đoàn khoa - Liên chi hội khoa Hóa học'::text,
        'Đoàn khoa - Liên chi hội khoa Sinh học'::text,
        'Đoàn khoa - Liên chi hội khoa Địa chất'::text,
        'Đoàn khoa - Liên chi hội khoa Vật lý'::text,
        'Facebook Khoa Công nghệ thông tin'::text,
        'Custom'::text
      ]
    )
  ),
  add constraint user_task_training_points_check check (
    type <> 'event'::text
    or source_platform = 'Custom'::text
    or (
      training_points is not null
      and training_points >= 0
      and training_points < 25
    )
  ),
  add constraint user_task_event_training_point_category_check check (
    type <> 'event'::text
    or source_platform = 'Custom'::text
    or (
      training_points = 0
      and training_point_category is null
    )
    or (
      training_points > 0
      and training_point_category is not null
    )
  ),
  add constraint user_task_estimated_hours_check check (
    type = any (array['class'::text, 'announcement'::text])
    or (
      type = 'assignment'::text
      and (estimated_hours is null or estimated_hours > 0)
    )
    or (
      type = 'event'::text
      and (
        source_platform = 'Custom'::text
        or (
          estimated_hours is not null
          and estimated_hours > 0
        )
      )
    )
  );

commit;
