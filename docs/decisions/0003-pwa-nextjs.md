# ADR-0003 · PWA con Next.js en lugar de app nativa

- **Estado:** Accepted
- **Fecha:** 2026-05-27
- **Bloquea:** F2 (PWA MVP)
- **Decide:** Equipo (heredado de PLAN.md §11)

## Contexto

El frontend debe servir a vendedores en la calle (móvil) y a gerencia (escritorio), con instalación fácil y un modo offline básico. Recursos de desarrollo limitados.

## Opciones consideradas

1. **PWA con Next.js 14 (App Router)** + manifest + service worker.
2. **Web tradicional + app nativa** (iOS + Android) en paralelo.
3. **Solo móvil nativo** (React Native o Flutter).

## Decisión

Adoptar (1). Una sola base sirve a web y móvil, se instala con un click desde el navegador, no requiere publicación en stores y soporta caching offline básico.

## Consecuencias

- Cero fricción de distribución (sin tiendas).
- Limitaciones de PWA en iOS (push notifications llegaron tarde, algunas APIs nativas faltan). Se acepta dado el caso de uso interno.
- Si en F7 se decide ir nativo, la lógica de UI puede portarse a React Native con esfuerzo razonable.
