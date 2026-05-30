# E5 · Memoria final del proyecto MotoShop

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulos cubiertos:** todos (2, 3, 4, 5)  
> **Estado:** ⬜ PENDIENTE cierre F6  
> **Última actualización:** 2026-05-30

---

## 1 · Por qué este doc está pendiente

E5 es la **memoria integradora final** del proyecto y se redacta como último paso, después de:

- F4-FIX1 cerrada (Prophet/Classifier auditados con métricas honestas).
- F5 cerrada (operación bidireccional PWA → sgHermes con app tables InnoDB).
- F6 cerrada (hardening + entrega académica + cierre de R6/R7/R8/R11/R12/R13).

Este archivo es el **esqueleto** que se irá completando en cada cierre de fase. Cada sección indica qué se va a poner y de dónde se va a traer.

---

## 2 · Estructura prevista

### 2.1 · Resumen ejecutivo (1 página)

Síntesis del proyecto en 5 párrafos. Fuente: [`docs/contexto-proyecto.md`](../contexto-proyecto.md) §15 (resumen ejecutivo en una frase) + bullet points por entregable.

### 2.2 · Contexto del negocio y diagnóstico inicial

Reusa contenido de [`E1-diagnostico-arquitectura.md`](E1-diagnostico-arquitectura.md) §1-4.

### 2.3 · Arquitectura técnica final

Reusa [`E1`](E1-diagnostico-arquitectura.md) §5-6 con actualizaciones post-F5/F6.

### 2.4 · Pipeline operativo

Reusa [`E2-pipeline-operativo.md`](E2-pipeline-operativo.md).

### 2.5 · Producto descriptivo

Reusa [`E3-producto-descriptivo.md`](E3-producto-descriptivo.md) con demo gerencial cerrada (R8) + demo 4G capturada (R6).

### 2.6 · Producto predictivo

Reusa [`E4-producto-predictivo.md`](E4-producto-predictivo.md) ratificado post-FIX1.

### 2.7 · Operación bidireccional (F5)

Por completar al cierre de F5:
- Tablas `app_*` en InnoDB.
- Endpoints PWA → sgHermes vía staging.
- RBAC fino.
- Tests E2E de escritura.

### 2.8 · Hardening + entrega (F6)

Por completar al cierre de F6:
- Workflow Databricks migrado (cierra R4).
- Monitoring / alerting / drift monitoring.
- Demo final a stakeholder.
- Demo 4G capturada.

### 2.9 · Lecciones aprendidas

Una sección por fase con lecciones técnicas + de proceso. Highlights anticipados:

**Lecciones técnicas:**
- El filtro de transformación silver puede esconder bugs catastróficos (F3.5 expuso 99.76% de pérdida silenciosa). Validar **universo completo bronze↔silver siempre**, no subsets.
- Forecasting por SKU con cola larga **no funciona**. Para repuestos con baja frecuencia, agregación por categoría es la dirección.
- Compute Free Edition + SQL Warehouse Serverless **es viable** para volúmenes medios (~30k filas por mart) sin pagar.
- Cloudflare Tunnel + PC local + Task Scheduler **es resiliente** suficiente para un MVP — pero no escala (F6 debería migrar a cloud).

**Lecciones de proceso:**
- Revisor + ejecutor como mismo agente sin contexto fresco **pierde el ojo crítico**. F4-B cerró verde con MAPE 3540% por esto.
- Ritmo de iteración alto sin pausas adversariales lleva a **deuda de audit**.
- Documentar lecciones en docs específicos NO basta — hay que **propagarlas al rulebook** del revisor inmediatamente.

### 2.10 · Riesgos vivos remanentes (post-F6)

Por documentar al cierre de F6 — los que queden tras cerrar R1-R13.

### 2.11 · Decisiones que cambiaríamos si empezáramos de nuevo

Por escribir al final. Anticipo:
- Cuadre silver↔bronze como gate explícito desde F2 (no esperar a F3.5).
- Sniff test de métricas ML como gate desde F4-A (no esperar a auditoría post-F4-B).
- Reviewer fresco (contexto independiente) como regla, no como excepción.
- Workflow Databricks desde F1.9, no diferido a F6 (R4).

### 2.12 · Roadmap post-curso

Visión 12-24 meses: F7 streaming, F8 multi-tienda, F9 marketplace.

### 2.13 · Bibliografía + recursos del curso

Por completar con las referencias usadas a lo largo del proyecto.

### 2.14 · Apéndices

- A. Glosario de términos del dominio (motopartes, sgHermes, MotoShop)
- B. Lista completa de ADRs aceptados
- C. Lista completa de riesgos R1-R13 con estado final
- D. Diagrama de arquitectura final (PNG/SVG)
- E. Capturas finales de PWA y dashboards
- F. Métricas finales (KPIs operativos + métricas ML auditadas)

---

## 3 · Cuándo se completa cada sección

| Sección | Fase que la completa | Fuente principal |
|---------|----------------------|-------------------|
| 2.1 Resumen ejecutivo | F6 | Todo este archivo |
| 2.2 Contexto + diagnóstico | F0/F1 (ya) | E1 |
| 2.3 Arquitectura técnica | F6 | E1 + actualizaciones |
| 2.4 Pipeline operativo | F2 (ya) | E2 |
| 2.5 Producto descriptivo | F3 (ya, ratificable post-R8) | E3 |
| 2.6 Producto predictivo | F4-FIX1 + F6 | E4 |
| 2.7 Operación bidireccional | F5 | A escribir |
| 2.8 Hardening + entrega | F6 | A escribir |
| 2.9 Lecciones | F6 | Recopilación + bitácora |
| 2.10 Riesgos remanentes | F6 | Tablero |
| 2.11 Decisiones que cambiaríamos | F6 | Reflexión final |
| 2.12 Roadmap post-curso | F6 | Reflexión final |
| 2.13 Bibliografía | F6 | Recopilación |
| 2.14 Apéndices | F6 | Recopilación + capturas |

---

## 4 · Convención de finalización

Cuando F6 cierre, este archivo se **reescribe completo** como documento integrador (no como esqueleto). El esqueleto actual sirve para que (a) el revisor sepa qué falta, (b) cuando volvamos en cada cierre de fase, sepamos qué agregar.

---

## 5 · Estado a 2026-05-30

- E1 ✅ Listo
- E2 ✅ Listo  
- E3 ✅ Listo (con V5/V6 diferidos a F6)
- E4 🟡 Pendiente cierre F4-FIX1
- E5 ⬜ Pendiente cierre F6

**Próximo paso:** cerrar F4-FIX1, luego ratificar E4. Después abrir F5.
