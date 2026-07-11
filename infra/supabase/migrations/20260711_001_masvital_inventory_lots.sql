-- Manual lot and expiry tracking for MasVital only.
-- Apply through the Supabase SQL editor or migration pipeline, never from the client.

create table if not exists public.app_inventory_lots (
    id uuid primary key default gen_random_uuid(),
    tenant text not null check (tenant = 'masvital'),
    product_sku text not null check (length(trim(product_sku)) > 0),
    purchase_order_ref text not null check (length(trim(purchase_order_ref)) > 0),
    lot_code text not null check (length(trim(lot_code)) > 0),
    expires_on date not null,
    received_on date not null default current_date,
    received_quantity numeric(14, 3) not null check (received_quantity > 0),
    remaining_quantity numeric(14, 3) not null check (remaining_quantity >= 0),
    supplier text,
    notes text,
    created_by text not null check (length(trim(created_by)) > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists app_inventory_lots_tenant_expiry_idx
    on public.app_inventory_lots (tenant, expires_on)
    where remaining_quantity > 0;
create index if not exists app_inventory_lots_tenant_sku_idx
    on public.app_inventory_lots (tenant, product_sku);

create table if not exists public.app_inventory_lot_movements (
    id uuid primary key default gen_random_uuid(),
    tenant text not null check (tenant = 'masvital'),
    lot_id uuid not null references public.app_inventory_lots(id) on delete restrict,
    movement_type text not null check (movement_type in ('receipt', 'adjustment')),
    quantity_delta numeric(14, 3) not null check (quantity_delta <> 0),
    remaining_after numeric(14, 3) not null check (remaining_after >= 0),
    reason text,
    idempotency_key uuid not null,
    request_fingerprint text not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
    created_by text not null check (length(trim(created_by)) > 0),
    created_at timestamptz not null default now(),
    unique (tenant, idempotency_key)
);

create index if not exists app_inventory_lot_movements_lot_idx
    on public.app_inventory_lot_movements (tenant, lot_id, created_at desc);

-- RLS is deliberate defense-in-depth. The API uses only the server-side
-- service-role credential; browser anon/auth roles have no table or RPC grants.
alter table public.app_inventory_lots enable row level security;
alter table public.app_inventory_lots force row level security;
alter table public.app_inventory_lot_movements enable row level security;
alter table public.app_inventory_lot_movements force row level security;

revoke all on table public.app_inventory_lots from anon, authenticated;
revoke all on table public.app_inventory_lot_movements from anon, authenticated;

create or replace function public.app_inventory_lot_receipt(
    p_tenant text,
    p_product_sku text,
    p_purchase_order_ref text,
    p_lot_code text,
    p_expires_on date,
    p_received_on date,
    p_received_quantity numeric,
    p_supplier text,
    p_notes text,
    p_created_by text,
    p_idempotency_key uuid,
    p_request_fingerprint text
) returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_lot public.app_inventory_lots;
    -- NOTE: a single generic `record` holds the replayed lot (as jsonb) plus the
    -- movement scalars. PL/pgSQL forbids a row-typed variable in a multi-item
    -- INTO list (ERROR 42601), so we never SELECT a whole row into it directly.
    v_existing record;
begin
    if p_tenant <> 'masvital' then
        raise exception 'expiry lots are available only for masvital' using errcode = '42501';
    end if;
    if p_received_quantity <= 0 then
        raise exception 'received quantity must be greater than zero' using errcode = '22023';
    end if;

    select to_jsonb(l) as lot_json, l.id as lot_id,
           m.movement_type as movement_type, m.request_fingerprint as request_fingerprint
    into v_existing
    from public.app_inventory_lot_movements m
    join public.app_inventory_lots l on l.id = m.lot_id
    where m.tenant = p_tenant and m.idempotency_key = p_idempotency_key;
    if found then
        if v_existing.movement_type <> 'receipt' then
            raise exception 'idempotency key was already used for another operation' using errcode = '22023';
        end if;
        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key was reused with a different request' using errcode = '22023';
        end if;
        return jsonb_build_object('replayed', true, 'lot', v_existing.lot_json);
    end if;

    insert into public.app_inventory_lots (
        tenant, product_sku, purchase_order_ref, lot_code, expires_on, received_on,
        received_quantity, remaining_quantity, supplier, notes, created_by
    ) values (
        p_tenant, trim(p_product_sku), trim(p_purchase_order_ref), trim(p_lot_code),
        p_expires_on, coalesce(p_received_on, current_date), p_received_quantity,
        p_received_quantity, nullif(trim(p_supplier), ''), nullif(trim(p_notes), ''), trim(p_created_by)
    ) returning * into v_lot;

    insert into public.app_inventory_lot_movements (
        tenant, lot_id, movement_type, quantity_delta, remaining_after,
        idempotency_key, request_fingerprint, created_by
    ) values (
        p_tenant, v_lot.id, 'receipt', p_received_quantity, p_received_quantity,
        p_idempotency_key, p_request_fingerprint, trim(p_created_by)
    );

    return jsonb_build_object('replayed', false, 'lot', to_jsonb(v_lot));
exception when unique_violation then
    select to_jsonb(l) as lot_json, l.id as lot_id,
           m.movement_type as movement_type, m.request_fingerprint as request_fingerprint
    into v_existing
    from public.app_inventory_lot_movements m
    join public.app_inventory_lots l on l.id = m.lot_id
    where m.tenant = p_tenant and m.idempotency_key = p_idempotency_key;
    if found then
        if v_existing.movement_type <> 'receipt' then
            raise exception 'idempotency key was already used for another operation' using errcode = '22023';
        end if;
        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key was reused with a different request' using errcode = '22023';
        end if;
        return jsonb_build_object('replayed', true, 'lot', v_existing.lot_json);
    end if;
    raise;
end;
$$;

create or replace function public.app_inventory_lot_adjustment(
    p_tenant text,
    p_lot_id uuid,
    p_quantity_delta numeric,
    p_reason text,
    p_created_by text,
    p_idempotency_key uuid,
    p_request_fingerprint text
) returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_lot public.app_inventory_lots;
    -- See note in app_inventory_lot_receipt: generic record, never a row var in
    -- a multi-item INTO list.
    v_existing record;
    v_remaining numeric(14, 3);
begin
    if p_tenant <> 'masvital' then
        raise exception 'expiry lots are available only for masvital' using errcode = '42501';
    end if;
    if p_quantity_delta = 0 then
        raise exception 'adjustment quantity must not be zero' using errcode = '22023';
    end if;

    select to_jsonb(l) as lot_json, l.id as lot_id,
           m.movement_type as movement_type, m.request_fingerprint as request_fingerprint
    into v_existing
    from public.app_inventory_lot_movements m
    join public.app_inventory_lots l on l.id = m.lot_id
    where m.tenant = p_tenant and m.idempotency_key = p_idempotency_key;
    if found then
        if v_existing.movement_type <> 'adjustment' then
            raise exception 'idempotency key was already used for another operation' using errcode = '22023';
        end if;
        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key was reused with a different request' using errcode = '22023';
        end if;
        if v_existing.lot_id <> p_lot_id then
            raise exception 'idempotency key was already used for a different lot' using errcode = '22023';
        end if;
        return jsonb_build_object('replayed', true, 'lot', v_existing.lot_json);
    end if;

    select * into v_lot
    from public.app_inventory_lots
    where id = p_lot_id and tenant = p_tenant
    for update;
    if not found then
        raise exception 'inventory lot not found' using errcode = 'P0002';
    end if;

    v_remaining := v_lot.remaining_quantity + p_quantity_delta;
    if v_remaining < 0 then
        raise exception 'adjustment would make remaining quantity negative' using errcode = '22023';
    end if;

    update public.app_inventory_lots
    set remaining_quantity = v_remaining, updated_at = now()
    where id = v_lot.id
    returning * into v_lot;

    insert into public.app_inventory_lot_movements (
        tenant, lot_id, movement_type, quantity_delta, remaining_after,
        reason, idempotency_key, request_fingerprint, created_by
    ) values (
        p_tenant, v_lot.id, 'adjustment', p_quantity_delta, v_remaining,
        nullif(trim(p_reason), ''), p_idempotency_key, p_request_fingerprint, trim(p_created_by)
    );

    return jsonb_build_object('replayed', false, 'lot', to_jsonb(v_lot));
exception when unique_violation then
    select to_jsonb(l) as lot_json, l.id as lot_id,
           m.movement_type as movement_type, m.request_fingerprint as request_fingerprint
    into v_existing
    from public.app_inventory_lot_movements m
    join public.app_inventory_lots l on l.id = m.lot_id
    where m.tenant = p_tenant and m.idempotency_key = p_idempotency_key;
    if found then
        if v_existing.movement_type <> 'adjustment' then
            raise exception 'idempotency key was already used for another operation' using errcode = '22023';
        end if;
        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key was reused with a different request' using errcode = '22023';
        end if;
        return jsonb_build_object('replayed', true, 'lot', v_existing.lot_json);
    end if;
    raise;
end;
$$;

revoke all on function public.app_inventory_lot_receipt(text, text, text, text, date, date, numeric, text, text, text, uuid, text) from public, anon, authenticated;
revoke all on function public.app_inventory_lot_adjustment(text, uuid, numeric, text, text, uuid, text) from public, anon, authenticated;
grant select, insert, update on public.app_inventory_lots to service_role;
grant select, insert on public.app_inventory_lot_movements to service_role;
grant execute on function public.app_inventory_lot_receipt(text, text, text, text, date, date, numeric, text, text, text, uuid, text) to service_role;
grant execute on function public.app_inventory_lot_adjustment(text, uuid, numeric, text, text, uuid, text) to service_role;
