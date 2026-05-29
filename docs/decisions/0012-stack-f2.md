# ADR-0012 · Stack técnico de Fase 2 (Silver + PWA MVP)

- **Estado:** Proposed
- **Fecha:** 2026-05-28
- **Bloquea:** F2-A, F2-B y F2-C

## Contexto

F2 tiene dos presiones al mismo tiempo: por un lado, el modelo Silver necesita limpieza y reglas de calidad; por el otro, la PWA debe salir rápido y funcionar bien sobre el stack que ya existe. El entorno también impone una restricción fuerte: el plan de Databricks disponible para el proyecto no depende de clusters tradicionales, así que la solución debe ser compatible con SQL Warehouse y con el flujo actual del repo.

## Decisión

### Silver

Vamos a materializar Silver con notebooks SQL sobre Databricks SQL Warehouse.

- Las dimensiones se resolverán con `MERGE INTO` por clave natural.
- Los hechos se resolverán con cargas idempotentes por partición o por llave de negocio, según el caso, evitando duplicados.
- Las reglas de calidad se expresarán en notebooks SQL y en evidencias versionadas, no con DLT.
- Las filas inválidas se documentarán o enviarán a cuarentena explícita cuando el caso lo pida.

### PWA

La PWA se construirá sobre el scaffold actual de Next.js App Router + TypeScript.

- La capa de datos usará `fetch` nativo con un wrapper pequeño para reintento de refresh cuando la API responda 401.
- La experiencia offline e instalable se resolverá con `next-pwa` para el MVP.
- No se introduce `axios` ni una capa de estado compleja mientras no haga falta.

## Opciones consideradas

### Silver: SQL Warehouse + notebooks vs DLT o PySpark

| Opción | Pros | Contras |
|--------|------|---------|
| SQL Warehouse + notebooks | Compatible con el entorno actual, fácil de reproducir, sin clusters | Más manual que DLT |
| DLT | Calidad declarativa y governance más natural | No encaja con el plan de compute actual |
| PySpark tradicional | Flexible para transformaciones complejas | Requiere compute que hoy no está disponible de forma natural |

### PWA: `next-pwa` vs service worker custom

| Opción | Pros | Contras |
|--------|------|---------|
| `next-pwa` | Salida rápida, menos código inicial | Depende del plugin |
| Service worker custom | Control fino | Más trabajo y más mantenimiento |

### Fetch: `fetch` nativo vs `axios`

| Opción | Pros | Contras |
|--------|------|---------|
| `fetch` nativo | Menos dependencias, suficiente para el MVP | Hay que envolver refresh/reintento |
| `axios` | Interceptors cómodos | Añade otra dependencia sin necesidad clara |

## Consecuencias

- F2-A puede arrancar con notebooks SQL y validar con evidencias legibles.
- La PWA puede avanzar sin introducir una pila extra de librerías.
- Si F2 crece más allá del MVP, esta ADR se revisa y se decide si se migra a DLT, a otra librería PWA o a un wrapper de datos más robusto.

## Próximo paso

Tomar esta ADR como base de implementación para F2-A y F2-B. Si una decisión cambia, se abre una nueva ADR o se actualiza esta con el nuevo contexto.
