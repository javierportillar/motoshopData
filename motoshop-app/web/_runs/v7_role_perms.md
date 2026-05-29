# V7 · Role Permissions — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿Los permisos de rol funcionan?
- **Resultado:** Pendiente de prueba con API real

## Setup implementado

- `middleware.ts` verifica cookie y redirige a `/login` si falta
- Header muestra nombre de usuario
- NavBar底部 muestra Inicio/Buscar/Perfil

## Próximos pasos

1. Login como `vendedor1`
2. Intentar acceder a endpoint admin (cuando exista) → 403
3. Verificar que `x-role` se inyecta correctamente
4. Documentar curls en `_runs/v7_role_perms.md`
