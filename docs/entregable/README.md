# Entregables académicos · Maestría IA & Ciencia de Datos · UAO 2025-2

> Set consolidado para el curso **Big Data y Transformación Digital del Negocio**.  
> Cada archivo corresponde a un entregable del curso (E1–E5) y referencia evidencia técnica del repo principal.  
> Última actualización: 2026-05-30 (Sesión 42).

---

## Índice

| ID | Título | Estado | Módulos del curso cubiertos |
|----|--------|--------|------------------------------|
| [E1](E1-diagnostico-arquitectura.md) | Diagnóstico organizacional + arquitectura técnica | ✅ Listo | Módulo 2 (criterios técnicos), Módulo 4 (madurez, VPC, BMC) |
| [E2](E2-pipeline-operativo.md) | Pipeline operativo end-to-end (ingesta → API → PWA) | ✅ Listo | Módulo 2 (escalabilidad, calidad, seguridad), Módulo 5 (gobernanza) |
| [E3](E3-producto-descriptivo.md) | Producto descriptivo (dashboards + KPIs) | ✅ Listo | Módulo 3 (analítica descriptiva), Módulo 4 (demo gerencial) |
| [E4](E4-producto-predictivo.md) | Producto predictivo (forecasting + alertas) | 🟡 Pendiente cierre F4-FIX1 | Módulo 3 (analítica predictiva + ética IA) |
| [E5](E5-memoria-final.md) | Memoria final del proyecto | ⬜ Pendiente cierre F6 | Todos los módulos |

---

## Cómo se relaciona con el repo principal

Este directorio es una **vista curada** del proyecto MotoShop para defensa académica. Los documentos:

- **NO duplican** evidencia técnica — referencian archivos en `notebooks/`, `motoshop-app/`, `docs/decisions/`, `notebooks/*/_runs/`.
- **SÍ explican** la decisión, contexto académico, criterios de evaluación y conexión con el marco conceptual del curso.

Si querés ver el detalle técnico, seguí los links a los archivos de evidencia.  
Si querés el master overview del proyecto, andá a [`docs/MASTER.md`](../MASTER.md).

---

## Convenciones

- **Evidencia versionada:** todo número, gráfica o cuadro reportado en estos docs está versionado en `_runs/` y referenciado con el archivo + commit.
- **Honestidad académica:** se documentan las limitaciones, deudas conscientes y errores de proceso. NO se inflan métricas.
- **Trazabilidad ADR:** cada decisión técnica linkea al ADR correspondiente en [`docs/decisions/`](../decisions/).
