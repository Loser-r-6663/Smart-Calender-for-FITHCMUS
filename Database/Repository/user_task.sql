-- Move per-user scheduling fields out of task content and into user_task_state.
-- Existing public.user_task rows and their IDs are preserved.
begin;

alter table public.user_task
  alter column source_platform drop not null,
  drop constraint if exists user_task_type_check,
  drop constraint if exists user_task_source_platform_check,
  drop constraint if exists user_task_training_points_check,
  drop constraint if exists user_task_event_training_point_category_check,
  drop constraint if exists user_task_estimated_hours_check,
  drop constraint if exists user_task_status_check;

update public.user_task
set source_platform = null
where source_platform = 'Custom';

update public.user_task
set source_platform = 'VNUHCMUS'
where source_platform = 'VNUHMCUS';

create table if not exists public.user_task_state (
  id uuid not null,
  user_id uuid not null,
  recurrence boolean not null default false,
  status text not null default 'proposed',
  compulsory boolean not null default false,
  flexible boolean not null default false,
  constraint user_task_state_pkey primary key (id, user_id),
  constraint user_task_state_user_id_fkey
    foreign key (user_id) references public.users (id) on delete cascade,
  constraint user_task_state_status_check
    check (status = any (array['scheduled'::text, 'proposed'::text, 'rejected'::text]))
);

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'user_task'
      and column_name in ('recurrence', 'status', 'compulsory', 'flexible')
  ) then
    insert into public.user_task_state (
      id, user_id, recurrence, status, compulsory, flexible
    )
    select
      task.id,
      task.user_id,
      coalesce((to_jsonb(task) ->> 'recurrence')::boolean, false),
      coalesce(to_jsonb(task) ->> 'status', 'proposed'),
      coalesce((to_jsonb(task) ->> 'compulsory')::boolean, false),
      coalesce((to_jsonb(task) ->> 'flexible')::boolean, false)
    from public.user_task as task
    on conflict (id, user_id) do update set
      recurrence = excluded.recurrence,
      status = excluded.status,
      compulsory = excluded.compulsory,
      flexible = excluded.flexible;
  end if;
end
$$;

alter table public.user_task
  drop column if exists recurrence,
  drop column if exists status,
  drop column if exists compulsory,
  drop column if exists flexible;

alter table public.user_task
  add constraint user_task_type_check check (
    type = any (
      array[
        'class'::text,
        'assignment'::text,
        'announcement'::text,
        'event'::text,
        'personal'::text
      ]
    )
  ),
  add constraint user_task_source_platform_check check (
    source_platform is null
    or source_platform = any (
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
        'Facebook Khoa Công nghệ thông tin'::text,
        'Custom'::text
      ]
    )
  ),
  add constraint user_task_training_points_check check (
    type <> 'event'::text
    or source_platform is null
    or source_platform = 'Custom'::text
    or (
      training_points is not null
      and training_points >= 0
      and training_points <= 24
    )
  ),
  add constraint user_task_event_training_point_category_check check (
    type <> 'event'::text
    or source_platform is null
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
    type = any (
      array['class'::text, 'announcement'::text, 'personal'::text]
    )
    or (
      type = 'assignment'::text
      and (estimated_hours is null or estimated_hours > 0)
    )
    or (
      type = 'event'::text
      and (
        source_platform is null
        or source_platform = 'Custom'::text
        or (
          estimated_hours is not null
          and estimated_hours > 0
        )
      )
    )
  );

create index if not exists user_task_user_id_idx
  on public.user_task using btree (user_id) tablespace pg_default;
create index if not exists user_task_type_idx
  on public.user_task using btree (type) tablespace pg_default;
create index if not exists user_task_deadline_idx
  on public.user_task using btree (deadline) tablespace pg_default;
create index if not exists user_task_source_platform_idx
  on public.user_task using btree (source_platform) tablespace pg_default;
create index if not exists user_task_state_user_id_idx
  on public.user_task_state using btree (user_id) tablespace pg_default;

commit;
