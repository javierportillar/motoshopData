-- Verificaciones de pago estampadas sobre una venta.
--
-- Vive en Supabase (no en el MySQL de cada nodo) porque el dato es compartido:
-- la misma venta se mira desde cualquier dispositivo. La clave es
-- (tenant, cod_clase, num_documento): reverificar actualiza, no acumula.
--
-- Sólo la escribe la API con la service-role key. El front nunca toca Supabase
-- directo: lee y escribe por los endpoints del backend.

create table if not exists public.bank_invoice_verifications (
  id               uuid primary key default gen_random_uuid(),
  tenant           text        not null,
  cod_clase        text        not null,
  num_documento    text        not null,
  fecha_venta      date        not null,
  valor            numeric(18,2) not null,
  estado           text        not null
                     check (estado in ('verificado', 'sin_coincidencia', 'ambiguo')),
  pagador          text,
  referencia       text,
  fecha_movimiento date,
  job_id           text,
  verificado_por   text        not null,
  verificado_at    timestamptz not null default now(),
  constraint bank_invoice_verifications_uq
    unique (tenant, cod_clase, num_documento)
);

create index if not exists bank_invoice_verifications_dia_idx
  on public.bank_invoice_verifications (tenant, fecha_venta);

-- RLS encendido y sin políticas: sólo la service-role key (el backend) entra.
-- La anon key no puede leer ni escribir esta tabla.
alter table public.bank_invoice_verifications enable row level security;

comment on table public.bank_invoice_verifications is
  'Verificación bancaria estampada sobre una factura. Se escribe sólo desde la API (service-role).';
