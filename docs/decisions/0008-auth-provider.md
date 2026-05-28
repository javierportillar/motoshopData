# ADR-0008 · Provider de autenticación (P4)

- **Estado:** **Proposed** — bloquea F1
- **Fecha:** 2026-05-27
- **Bloquea:** F1 (auth JWT + roles)
- **Decide:** Humano (responsable del proyecto)

## Contexto

La PWA necesita login con tres roles: admin, vendedor, gerente. Los usuarios son internos (no clientes finales todavía). Hay que decidir si construimos el login en casa o delegamos en un identity provider externo.

## Opciones consideradas

### A · Login propio (email + password con bcrypt + JWT)

- Tabla `app_usuarios` (cuando llegue F5; mientras tanto, archivo o tabla simple).
- JWT con expiración corta + refresh tokens.
- **Pros:** cero dependencias externas; control total; no requiere que los usuarios tengan cuenta Google/Microsoft.
- **Contras:** somos nosotros quienes gestionamos contraseñas, recuperación, lockouts, 2FA si llega a hacer falta; superficie de ataque que mantener.

### B · Google Identity (OAuth)

- Los usuarios entran con su cuenta Google.
- **Pros:** delega el problema duro (passwords, 2FA, recuperación) a Google; UX moderna.
- **Contras:** requiere que cada vendedor tenga cuenta Google y que el negocio acepte ese vínculo; configuración inicial de OAuth en Google Cloud Console.

### C · Microsoft Entra ID (antes Azure AD)

- Mismo modelo que B pero con Microsoft.
- **Pros/Contras:** equivalentes a B; útil si el negocio ya usa Microsoft 365.

## Recomendación

**Opción A para F1** (login propio, simple, sin depender de terceros para empezar), **con la puerta abierta a sumar B o C en F6** cuando la base esté estabilizada y haya feedback real de usuarios. JWT + bcrypt + rate limiting + auditoría de intentos fallidos cubre los requisitos académicos y operativos iniciales.

## Consecuencias si se acepta A

- Hay que diseñar el flujo de creación de usuarios (¿manual por admin? ¿invitación por correo?).
- Hay que definir política de contraseñas y recuperación.
- Hay que registrar `app_audit_log` de logins desde F5.
- Migrar a OAuth más adelante es factible (los `user_id` permanecen).
