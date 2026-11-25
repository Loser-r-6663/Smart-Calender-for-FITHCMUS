-- Passwords are stored as scrypt hashes by Database.py.
-- Credential and session columns are encrypted by the application before
-- they are sent to Supabase.

begin;

create extension if not exists pgcrypto;

create table if not exists public.users (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    
    username text not null unique,

    portal_username text,
    portal_password text,
    moodle_session text,
    moodle_status boolean not null default false,
    portal_session text,
    portal_status boolean not null default false,
    training_points jsonb not null default '{"Articles 1": 0, "Articles 2": 0, "Articles 3": 0, "Articles 4": 0, "Articles 5": 0}'::jsonb
);

alter table public.users
    add column if not exists training_points jsonb not null
    default '{"Articles 1": 0, "Articles 2": 0, "Articles 3": 0, "Articles 4": 0, "Articles 5": 0}'::jsonb;

create index if not exists users_username_idx
    on public.users (username);

commit;
