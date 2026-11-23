-- Migration: Hỗ trợ User Input Task (travel_buffer_minutes) & Lưu chỉnh sửa lịch (Pin / Reject / Reschedule)
-- Chạy script này trong Supabase SQL Editor.

-- 1. Thêm cột thời gian di chuyển ước tính (phút) cho bảng user_task
ALTER TABLE IF EXISTS public.user_task
    ADD COLUMN IF NOT EXISTS travel_buffer_minutes integer CHECK (travel_buffer_minutes IS NULL OR travel_buffer_minutes >= 0);

-- 1b. Thêm cột lưu điểm rèn luyện hiện có theo 5 tiêu chí (dieu_1..dieu_5) cho bảng users
ALTER TABLE IF EXISTS public.users
    ADD COLUMN IF NOT EXISTS drl_scores jsonb NOT NULL DEFAULT '{"dieu_1": 0, "dieu_2": 0, "dieu_3": 0, "dieu_4": 0, "dieu_5": 0}'::jsonb;

-- 2. Tạo bảng lưu tùy chỉnh lịch của từng user cho các task công khai/cá nhân
CREATE TABLE IF NOT EXISTS public.user_task_preferences (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task_id text NOT NULL,
    pin_status text NOT NULL DEFAULT 'default' CHECK (pin_status IN ('default', 'pinned', 'rejected')),
    custom_start_at timestamptz NULL,
    custom_end_at timestamptz NULL,
    travel_buffer_minutes integer NULL CHECK (travel_buffer_minutes IS NULL OR travel_buffer_minutes >= 0),
    is_scheduled boolean NOT NULL DEFAULT false,
    scheduled_start_at timestamptz NULL,
    scheduled_end_at timestamptz NULL,
    points_gained integer NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, task_id)
);

-- Bổ sung 4 cột kết quả xếp lịch nếu bảng user_task_preferences đã tồn tại từ trước
ALTER TABLE IF EXISTS public.user_task_preferences
    ADD COLUMN IF NOT EXISTS is_scheduled boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS scheduled_start_at timestamptz NULL,
    ADD COLUMN IF NOT EXISTS scheduled_end_at timestamptz NULL,
    ADD COLUMN IF NOT EXISTS points_gained integer NULL;

CREATE INDEX IF NOT EXISTS idx_user_task_preferences_user_id
    ON public.user_task_preferences (user_id);

-- 3. Bật Row Level Security (RLS) để mỗi user chỉ đọc/ghi được preferences của chính mình
ALTER TABLE public.user_task_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own task preferences" ON public.user_task_preferences;
CREATE POLICY "Users can view own task preferences"
    ON public.user_task_preferences
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own task preferences" ON public.user_task_preferences;
CREATE POLICY "Users can insert own task preferences"
    ON public.user_task_preferences
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own task preferences" ON public.user_task_preferences;
CREATE POLICY "Users can update own task preferences"
    ON public.user_task_preferences
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own task preferences" ON public.user_task_preferences;
CREATE POLICY "Users can delete own task preferences"
    ON public.user_task_preferences
    FOR DELETE
    USING (auth.uid() = user_id);
