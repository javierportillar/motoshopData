-- Private, tenant-scoped monthly forecast vintages for leak-free daily backtests.
create table if not exists public.sales_forecast_vintages (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  forecast_month date not null
    check (forecast_month = date_trunc('month', forecast_month)::date),
  forecast_origin_date date not null,
  run_kind text not null
    check (run_kind in ('issued', 'reconstructed')),
  model_version text not null,
  calibration_version text not null,
  source_cutoffs jsonb not null default '{}'::jsonb,
  daily_forecast jsonb not null
    check (jsonb_typeof(daily_forecast) = 'array'),
  monthly_base_amount numeric(18, 2) not null,
  calibration jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint sales_forecast_vintages_canonical_month_key
    unique (tenant_id, forecast_month),
  constraint sales_forecast_vintages_id_tenant_key unique (id, tenant_id)
);

create index if not exists sales_forecast_vintages_tenant_month_idx
  on public.sales_forecast_vintages (tenant_id, forecast_month desc, created_at desc);

alter table public.sales_forecast_vintages enable row level security;
revoke all on table public.sales_forecast_vintages from public, anon, authenticated;
grant select, insert on table public.sales_forecast_vintages to service_role;

comment on table public.sales_forecast_vintages is
  'Server-only immutable monthly forecast vintages with source cutoffs and post-close evaluation.';

create table if not exists public.sales_forecast_evaluations (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  vintage_id uuid not null,
  sales_cutoff date not null,
  actual_fingerprint text not null,
  actual_daily jsonb not null
    check (jsonb_typeof(actual_daily) = 'array'),
  metrics jsonb not null default '{}'::jsonb,
  evaluated_at timestamptz not null default now(),
  constraint sales_forecast_evaluations_vintage_tenant_fk
    foreign key (vintage_id, tenant_id)
    references public.sales_forecast_vintages (id, tenant_id)
    on delete cascade,
  constraint sales_forecast_evaluations_snapshot_key
    unique (vintage_id, actual_fingerprint)
);

create index if not exists sales_forecast_evaluations_tenant_cutoff_idx
  on public.sales_forecast_evaluations (tenant_id, sales_cutoff desc, evaluated_at desc);

alter table public.sales_forecast_evaluations enable row level security;
revoke all on table public.sales_forecast_evaluations from public, anon, authenticated;
grant select, insert on table public.sales_forecast_evaluations to service_role;

comment on table public.sales_forecast_evaluations is
  'Append-only daily evaluation snapshots; corrected actuals create a new fingerprinted row.';
