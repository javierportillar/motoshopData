# Plan F7 · Reestructuración + Diseño + Mobile-first

- **Fecha apertura:** 2026-05-30 (Sesión 50)
- **Estado:** 🟡 ABIERTA (decision humana 2026-05-30 — extiende roadmap más allá de F6)
- **Origen:** después de cerrar F6-D (cloud híbrido) y detectar bugs UX, vos pediste una fase nueva para:
  - Definición clara de tipos de tableros y variables a indicar
  - Rediseño UI/UX
  - Mobile web (responsive real, no breakpoints accidentales)
- **Dependencia obligatoria:** F6-D-FIX1 ✅ (los 3 bugs operativos NO pueden quedar abiertos antes de rediseñar)
- **Duración estimada:** 3 sprints. Discovery 1-2h + Design 2-3h + Implementation 4-6h. Wall-clock ~8-12 h con paralelización.

---

## 1 · Por qué F7 existe

F2 → F5 entregaron funcionalidad. F6-D entregó arquitectura híbrida. **Pero la UX siguió siendo táctica:** dashboards agregados ad-hoc según se necesitaron, sin sistema de diseño, sin definir prioridades visuales, con formatters arbitrarios (Bug 2 de F6-D-FIX1).

F7 es **el sprint donde MotoShop pasa de "funcional" a "presentable"** ante stakeholders externos (gerencia + jurado académico + posibles compradores del SaaS si decidieras venderlo).

Sin F7, la app es defendible técnicamente (F4 predictivo, F5 escritura, F6 cloud) pero **NO es defendible visualmente** ante un decisor de negocio. El humano notó esto de primera mano cuando vio "$0.0M con 911 facturas".

---

## 2 · Scope y NO scope

### Lo que SÍ entrega F7

**F7-A · Discovery (revisor + humano):**
- Mapeo de **personas de uso** (vendedor en mostrador, gerente en oficina, dueño en su celular)
- Lista de **KPIs prioritarios** por persona (5-7 por dashboard, no 20)
- Definición de **tipos de tableros** que se necesitan vs los que existen
- Audit visual de las 4 pages actuales con screenshots + observaciones
- Decisión de **branding** (colores, tipografía, logo, tono)

**F7-B · Design tokens + sistema (Dev T design):**
- `motoshop-app/web/lib/design/tokens.ts` con paleta, spacing, typography
- Componentes base: `Card`, `Stat`, `Table`, `Chart`, `Badge`
- Stories en formato lightweight (no Storybook full — markdown + capturas)
- Tema light + dark si humano lo pide

**F7-C · Implementación dashboards (Dev T):**
- Migrar las 4 pages existentes (`ventas`, `inventario`, `abc`, `dormidos`) al nuevo sistema
- Crear las nuevas pages que F7-A definió (si aplica)
- **Mobile-first real:** breakpoints definidos (`sm: 640px`, `md: 768px`, `lg: 1024px`) + touch targets ≥ 44px + bottom navigation para móvil + sidebar para desktop
- Charts responsivos (recharts ya soporta `<ResponsiveContainer>`)
- Tests E2E Playwright en 3 viewports: mobile (375px), tablet (768px), desktop (1280px)

### Lo que NO entra en F7

- Nuevos endpoints backend (a menos que F7-A descubra que faltan datos)
- Cambios al pipeline de datos (silver/gold)
- Multi-idioma / i18n
- Tema dark obligatorio (opcional según F7-A)
- A11y AAA (mínimo a11y AA: focus visible, contraste 4.5:1, labels semánticos)
- Internacionalización de monedas (queda en `es-CO`)
- Performance ultra-optimizada (Lighthouse > 95) — meta es > 85 en mobile

---

## 3 · Decisiones técnicas pendientes (DT-F7-X · a decidir en F7-A)

Estas decisiones NO las propongo de antemano. Salen del discovery con vos:

1. **¿Cuántos tableros vamos a tener al final?** Hoy: 4 (ventas, inventario, abc, dormidos). ¿Sumamos forecast, alerts, cohortes, drift? ¿O consolidamos?
2. **¿Quién es la "persona" principal?** Si es vendedor en mostrador → priorizamos consulta rápida + voice search. Si es gerente → priorizamos overview + drill-down.
3. **¿Hay branding existente?** ¿MotoShop tiene logo? ¿Colores corporativos? ¿O empezamos limpio?
4. **¿Tema dark?** Más esfuerzo. Solo si humano confirma valor.
5. **¿Bottom navigation o sidebar?** Mobile vs desktop pattern.
6. **¿Mantenemos recharts o probamos visx / nivo?** recharts es ligero pero limitado en visual.

---

## 4 · Sprints

### Sprint F7-A · Discovery (Revisor + Humano · ~1-2 h)

**Paso A1 · Audit visual actual (~30 min, revisor)**
- Tomar screenshots de las 4 pages actuales en 3 viewports (mobile, tablet, desktop)
- Documentar observaciones en `docs/f7/audit_visual_<ts>.md`:
  - ¿Qué se ve mal en mobile?
  - ¿Hay textos cortados?
  - ¿Touch targets demasiado chicos?
  - ¿Colores accesibles?

**Paso A2 · Definición personas + KPIs (~30 min, humano + revisor)**
- Sesión rápida (videocall o chat): definir 2-3 personas
- Por persona, listar 5-7 KPIs prioritarios
- Mapear KPIs a endpoints existentes (¿hay datos? ¿faltan?)
- Output: `docs/f7/personas_kpis.md`

**Paso A3 · Decisiones de branding (~30 min, humano)**
- ¿Hay logo? ¿Hay colores existentes?
- Si no, decidir: paleta (recomendación: 1 primario, 1 secundario, escala de grises)
- Tipografía: ¿Inter, Roboto, sans-serif system? Recomendación: system + Inter como fallback
- Output: `docs/f7/branding.md` con tokens definidos

**Paso A4 · Plan implementación detallado (~30 min, revisor)**
- Con personas + KPIs + branding, listar exactamente:
  - Qué pages quedan, cuáles se agregan, cuáles se eliminan
  - Componentes base necesarios
  - Cronograma F7-B y F7-C
- Output: `docs/f7/implementation_plan.md`

### Sprint F7-B · Design system (Dev T · ~2-3 h)

**Paso B1 · Tokens (~45 min)**
- `motoshop-app/web/lib/design/tokens.ts` con:
  - `colors`: primary, secondary, success, warning, error, neutral 50-900
  - `spacing`: 4, 8, 12, 16, 24, 32, 48, 64 (px)
  - `typography`: heading 1-4, body, small, mono
  - `radius`, `shadow`, `breakpoints`
- Integración con Tailwind config

**Paso B2 · Componentes base (~1.5 h)**
- `components/ui/Card.tsx`
- `components/ui/Stat.tsx` (KPI con valor + delta + sparkline opcional)
- `components/ui/Table.tsx` (responsive: tabla en desktop, cards stack en mobile)
- `components/ui/Badge.tsx`
- `components/ui/Chart.tsx` (wrapper recharts con tokens)

**Paso B3 · Stories markdown (~30 min)**
- `docs/f7/components/<name>.md` con: descripción, props, ejemplo de uso, captura

### Sprint F7-C · Migración pages + mobile-first (Dev T · ~4-6 h)

**Paso C1 · Migrar `/dashboards/ventas` (~1 h)**
- Aplicar nuevo design system
- Mobile-first: layout stack en mobile, grid en desktop
- Chart responsive
- Touch targets ≥ 44px

**Paso C2 · Migrar `/dashboards/inventario`, `/abc`, `/dormidos` (~2 h)**
- Mismo patrón
- Reutilizar componentes base

**Paso C3 · Nuevas pages si F7-A las definió (~1-2 h)**

**Paso C4 · Bottom navigation mobile + sidebar desktop (~30 min)**
- Componente `Navigation` adaptable
- Selección de tab activa

**Paso C5 · E2E Playwright 3 viewports (~30 min)**
- `motoshop-app/web/tests/responsive.spec.ts`:
  - 375px (mobile)
  - 768px (tablet)
  - 1280px (desktop)
- Verifica: navegación, layout no roto, charts visibles, touch targets

**Paso C6 · Lighthouse audit (~15 min)**
- Mobile Lighthouse > 85
- A11y > 90
- Best Practices > 90

**Paso C7 · Deploy + smoke (~15 min)**
- `npx vercel --prod`
- Smoke desde celular 4G real
- Evidencia en `motoshop-app/web/_runs/v_f7_responsive_<ts>.md`

---

## 5 · V críticas

| ID | Verificación | Pass criterion |
|----|--------------|---------------|
| **V-F7-1** | Discovery completo | `docs/f7/personas_kpis.md` + `branding.md` + `implementation_plan.md` aprobados por humano |
| **V-F7-2** | Tokens definidos | `tokens.ts` con colors/spacing/typography integrados con Tailwind |
| **V-F7-3** | 5 componentes base | `Card`, `Stat`, `Table`, `Badge`, `Chart` con stories |
| **V-F7-4** | 4 pages migradas | Ventas/inventario/abc/dormidos usando nuevo system |
| **V-F7-5** | Mobile-first verificado | Lighthouse Mobile > 85 + Playwright 3 viewports verde |
| **V-F7-6** | A11y mínimo AA | Focus visible, contraste 4.5:1, labels en inputs y botones |
| **V-F7-7** | Demo mobile real | Vos abrís `https://app.fragloesja.uk` desde celular 4G y la UX es notablemente mejor que pre-F7 |

**Gate:** V-F7-1 a V-F7-7 PASS para cerrar F7.

---

## 6 · Riesgos

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| R-F7-1 | F7-A se estanca en decisiones humanas | Timebox 2h max. Si no hay decisión, revisor propone default y vos validás. |
| R-F7-2 | Scope creep (humano pide funcionalidad no planeada) | Defender el "NO scope" de §2. Lo nuevo va a F8. |
| R-F7-3 | Migración rompe pages existentes | Tests E2E ya cubren `/dashboards/*` actuales. Detecta regresiones. |
| R-F7-4 | Lighthouse <85 mobile | Optimizar imágenes + lazy-load charts + reducir JS bundle. |
| R-F7-5 | Componentes mal abstraídos requiere refactor | F7-B paso B3 (stories) fuerza pensar primero, código después. |

---

## 7 · Handoffs

### 👤 Handoff #1 · Humano · Sprint F7-A Discovery (~1-2 h)

Vos sos protagonista del discovery. Conmigo (revisor) en chat:

1. Vos: respondés las 6 preguntas de §3 (DT-F7-X)
2. Revisor: hace audit visual de las 4 pages actuales + screenshots
3. Conjuntamente: definimos personas + KPIs + branding
4. Revisor: escribe los 3 docs (`personas_kpis.md`, `branding.md`, `implementation_plan.md`)
5. Vos aprobás → arranca F7-B

**Cuándo arrancar:** después que F6-D-FIX1 cierre verde. NO antes — los bugs operativos primero.

### 🤖 Handoff #2 · Dev T · Sprint F7-B Design system (~2-3 h)

Se redacta DESPUÉS de cerrar F7-A. Necesita los outputs del discovery para tener scope concreto.

### 🤖 Handoff #3 · Dev T · Sprint F7-C Implementación (~4-6 h)

Se redacta DESPUÉS de cerrar F7-B. Necesita los componentes para migrar las pages.

---

## 8 · Cierre + audit

Una vez F7-C cierre:

1. Revisor audita las 7 V-F7 con sus 9 checks habituales (`INICIAR_REVIEWER.md`).
2. Vos hacés "demo 4G post-F7" para tu propio comparativo: ¿se ve mejor que pre-F7?
3. Si ✅ → F7 cerrada, repositorio queda en estado **presentable + defendible**.
4. Esto + las demos R6/R8 cierran la entrega académica.

---

## 9 · Estado proyectado tras F7 cerrada

```
F0 ✅  F1 ✅ (+F1.5 ✅ +F1.9 ✅)  F2 ✅  F3 ✅ (+F3.5 ✅ +F3.6 ✅)
F4-A ✅ F4-B ✅ F4-C ✅ F4-FIX1 ✅
F5 ✅ F5-FIX1 ✅
F6-A ✅ F6-B ✅ F6-C ✅ F6-D ✅ F6-D-FIX1 ✅
F7-A ✅ F7-B ✅ F7-C ✅

7/7 fases originales + 6 hardening sprints + reestructuración UX
```

**Después de F7:** la PWA está lista para mostrarse a cualquier audiencia (gerencia, jurado, posibles compradores). E5 memoria final con capturas finales del nuevo UI.

---

## 10 · Decisión humana inicial

Antes de arrancar F7-A, confirmá:

- [ ] **F7 va antes o después de la defensa académica?** Si va antes, hay que apurar (~3 días). Si va después, podemos respirar.
- [ ] **¿Tenés deadlines duros?** Fecha exacta de defensa.
- [ ] **¿Tenés branding existente** (logo MotoShop, colores) o empezamos desde cero?
