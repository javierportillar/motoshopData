"""Router CRUD para gastos operativos.

Permisos:
  - admin/gerente: crear, editar, eliminar
  - todos los roles autenticados: listar

Multi-tenant: el tenant se infiere del header X-Tenant. Las queries
filtran por tenant tanto en lectura como en escritura.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.gastos.schemas import (
    CATEGORIAS_VALIDAS,
    CategoriasResponse,
    CopiarGastosRequest,
    GastoCreate,
    GastoResponse,
    GastoUpdate,
    GastosListResponse,
)
from motoshop_api.gastos.supabase_client import (
    copy_gastos,
    create_gasto,
    delete_gasto,
    list_gastos,
    update_gasto,
)

router = APIRouter(prefix="/api/gastos", tags=["gastos"])


@router.get("/categorias", response_model=CategoriasResponse)
def get_categorias(
    _user: User = Depends(get_current_user),
) -> CategoriasResponse:
    """Catálogo de categorías de gastos predefinidas."""
    return CategoriasResponse(categorias=sorted(CATEGORIAS_VALIDAS))


@router.get("", response_model=GastosListResponse)
def get_gastos(
    mes: str | None = Query(default=None, description="YYYY-MM"),
    categoria: str | None = Query(default=None),
    fecha_inicio: str | None = Query(default=None, description="YYYY-MM-DD"),
    fecha_fin: str | None = Query(default=None, description="YYYY-MM-DD"),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> GastosListResponse:
    """Lista gastos del tenant con filtros opcionales."""
    items = list_gastos(
        tenant=tenant,
        mes=mes,
        categoria=categoria.lower() if categoria else None,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    return GastosListResponse(
        items=[GastoResponse(**i) for i in items],
        total=len(items),
    )


@router.post("", response_model=GastoResponse, status_code=201)
def post_gasto(
    payload: GastoCreate,
    user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_tenant),
) -> GastoResponse:
    """Crea un gasto operativo. Solo admin/gerente."""
    created = create_gasto(
        tenant=tenant,
        payload=payload.model_dump(),
        created_by=user.username,
    )
    return GastoResponse(**created)


@router.post("/copiar", response_model=GastosListResponse, status_code=201)
def copiar_gastos(
    payload: CopiarGastosRequest,
    user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_tenant),
) -> GastosListResponse:
    """Copia los gastos de un mes a otro. Solo admin/gerente.

    Omite duplicados ya presentes en el mes destino. Devuelve los creados.
    """
    if payload.mes_origen == payload.mes_destino:
        raise HTTPException(status_code=400, detail="El mes origen y destino no pueden ser iguales")
    creados = copy_gastos(
        tenant=tenant,
        mes_origen=payload.mes_origen,
        mes_destino=payload.mes_destino,
        created_by=user.username,
        ids=payload.ids,
    )
    return GastosListResponse(
        items=[GastoResponse(**g) for g in creados],
        total=len(creados),
    )


@router.patch("/{gasto_id}", response_model=GastoResponse)
def patch_gasto(
    gasto_id: int,
    payload: GastoUpdate,
    _user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_tenant),
) -> GastoResponse:
    """Actualiza un gasto. Solo admin/gerente."""
    if gasto_id <= 0:
        raise HTTPException(status_code=400, detail="id inválido")
    updated = update_gasto(
        tenant=tenant,
        gasto_id=gasto_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return GastoResponse(**updated)


@router.delete("/{gasto_id}", status_code=204)
def del_gasto(
    gasto_id: int,
    _user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_tenant),
) -> None:
    """Elimina un gasto. Solo admin/gerente."""
    if gasto_id <= 0:
        raise HTTPException(status_code=400, detail="id inválido")
    delete_gasto(tenant=tenant, gasto_id=gasto_id)
    return None
