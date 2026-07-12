-- Application users for role/module-based access control (RBAC).
-- Hybrid model: this table is the source of truth for user CRUD from the app;
-- the legacy users.yaml keeps working until users are re-created here.
-- Apply through the Supabase SQL editor or migration pipeline, never from the client.

create table if not exists public.app_users (
    username text primary key check (length(trim(username)) > 0),
    hashed_password text not null check (length(trim(hashed_password)) > 0),
    email text not null default '',
    role text not null check (role in ('admin', 'gerente', 'vendedor')),
    -- Tenants the user may switch to. Empty array = no restriction (all tenants).
    tenants_allowed jsonb not null default '[]'::jsonb,
    -- Feature/module keys the user may see. Empty array = no modules (admins bypass).
    allowed_modules jsonb not null default '[]'::jsonb,
    active boolean not null default true,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists app_users_active_idx on public.app_users (active);

-- RLS is defense-in-depth: the API uses only the server-side service-role
-- credential; browser anon/auth roles get no grants and cannot read password hashes.
alter table public.app_users enable row level security;
alter table public.app_users force row level security;

revoke all on table public.app_users from anon, authenticated;
grant select, insert, update, delete on table public.app_users to service_role;

-- Seed the existing admin so it can be managed from the app too. bcrypt hash of
-- the current password (FG28). on conflict do nothing: never clobber an edited admin.
insert into public.app_users (username, hashed_password, email, role, tenants_allowed, allowed_modules, active, created_by)
values (
    'admin',
    '$2b$12$pfNJ1ebNx.YDbTMBgHjFU.GJaK2TReoB1Hn06//4hOtNqt/8zSdcS',
    'admin@fragloesja.uk',
    'admin',
    '["motoshop", "masvital"]'::jsonb,
    '[]'::jsonb,
    true,
    'migration'
)
on conflict (username) do nothing;
