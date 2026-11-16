-- Passwords are stored as scrypt hashes by Database.py.
-- Credential and session columns are encrypted by the application before
-- they are sent to Supabase.

begin;

create extension if not exists pgcrypto;

create table if not exists public.users (
    user_id uuid primary key default gen_random_uuid(),
    username text not null unique,
    password_hash text not null,

    portal_username text,
    portal_password text,
    moodle_session text,
    moodle_status boolean not null default false,
    portal_session text,
    portal_status boolean not null default false
);

create index if not exists users_username_idx
    on public.users (username);

commit;
