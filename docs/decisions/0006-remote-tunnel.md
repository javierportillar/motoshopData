# ADR-0006 · Túnel remoto para exponer la API (P2)

- **Estado:** **Accepted** — 2026-05-27
- **Fecha:** 2026-05-27
- **Bloquea:** F0 (entregable Track T · "Llamada HTTPS desde red externa exitosa")
- **Decide:** Humano (responsable del proyecto)

## Contexto

La API FastAPI corre en el PC junto al MySQL. No queremos abrir puertos del router doméstico. Necesitamos que un celular fuera de la red local pueda hacer login y consultar stock (hito de F1).

## Opciones consideradas

### A · Cloudflare Tunnel *(recomendado por PLAN §11)*

- `cloudflared` corre en el PC y publica el servicio en un subdominio gratis de `*.trycloudflare.com` o en un dominio propio.
- **Pros:** gratis (free tier generoso); HTTPS automático; no abre puertos; soporta WAF y rate limiting de Cloudflare; auditoría de peticiones; cero infra adicional.
- **Contras:** dependencia de Cloudflare como third-party; subdominio público; el servicio queda atado a su disponibilidad.

### B · Tailscale

- VPN mesh, solo dispositivos autorizados ven la API.
- **Pros:** privado por defecto; cero exposición pública; cliente fácil en iOS/Android.
- **Contras:** cada dispositivo (vendedor, gerencia) necesita cliente Tailscale instalado; menos amigable para usuarios no técnicos; free tier limita dispositivos.

### C · VPS pequeño con SSH tunnel inverso

- Un VPS público (DigitalOcean, Hetzner) recibe el tráfico y lo reenvía por SSH al PC.
- **Pros:** control total; aprende cómo funciona el reverse proxy.
- **Contras:** infra que mantener; coste mensual; superficie de ataque mayor; complejidad de operar el túnel SSH 24/7.

## Recomendación

**Opción A — Cloudflare Tunnel.** Es lo más rápido de poner en marcha, lo más seguro por defecto (no expone puertos del router), gratis para este volumen y se integra con un dominio propio cuando se quiera. Tailscale (B) se puede sumar en F6 como vía privada para gerencia si hace falta.

## Consecuencias si se acepta A

- Hay que crear cuenta Cloudflare y ejecutar `cloudflared service install` con un token.
- El token vive en `.env` (NUNCA en Git).
- En F6 se evalúa pasar a dominio propio + WAF rules más estrictas.
