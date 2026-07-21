-- Privileged deletion for MasVital manual expiry lots.
-- The API calls this with the server-side service role only; browser roles keep no grants.

create or replace function public.app_inventory_lot_delete(
    p_tenant text,
    p_lot_id uuid
) returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_lot public.app_inventory_lots;
begin
    if p_tenant <> 'masvital' then
        raise exception 'expiry lots are available only for masvital' using errcode = '42501';
    end if;

    select * into v_lot
    from public.app_inventory_lots
    where id = p_lot_id and tenant = p_tenant
    for update;
    if not found then
        raise exception 'inventory lot not found' using errcode = 'P0002';
    end if;

    delete from public.app_inventory_lot_movements
    where tenant = p_tenant and lot_id = p_lot_id;

    delete from public.app_inventory_lots
    where id = p_lot_id and tenant = p_tenant;

    return jsonb_build_object('deleted', true, 'lot', to_jsonb(v_lot));
end;
$$;

revoke all on function public.app_inventory_lot_delete(text, uuid) from public, anon, authenticated;
grant execute on function public.app_inventory_lot_delete(text, uuid) to service_role;
