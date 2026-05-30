# F7-A · Implementation Plan (Discovery output)

- **Fecha:** 2026-05-30 (Sesión 50)
- **Status:** Approved (humano validó timeline 1-2 semanas)
- **Outputs A2-A4:** [personas_kpis.md](personas_kpis.md), [branding.md](branding.md), este documento

---

## 1 · Cronograma realista 1-2 semanas

| Día | Sprint | Actor | Entregable |
|-----|--------|-------|-----------|
| **Día 1 (HOY)** | F7-A Discovery | Revisor + humano | ✅ personas_kpis.md, branding.md, implementation_plan.md |
| Día 1 (paralelo) | F6-D-FIX1 | Dev A + Dev T | Bugs producción (404 dormidos, formatter $0.0M, valor inventario) |
| Día 1-2 (humano) | Subir assets | Humano | `docs/f7/branding/logo.svg` + `colors.md` |
| Día 2 (paralelo) | Demo 4G (R6) | Humano | Grabar video 5 min en celular 4G real |
| Día 2-4 | F7-B Design system | Dev T | Tokens + 5 componentes base + stories |
| Día 3-5 (paralelo) | Demo gerencia (R8) | Humano | Sesión con stakeholder + feedback capturado |
| Día 4-7 | F7-C Implementación | Dev T | Migrar 8 pages + crear `/plan-compras` + responsive + Lighthouse > 85 |
| Día 5-7 | E5 memoria final | Revisor | ~30-50 págs con capturas post-F7 |
| Día 7-10 | Audit final cierre proyecto | Revisor | Veredicto cierre + commit final |
| Día 11-14 | Buffer + ensayo defensa | Humano | Practicar narrativa + responder objeciones probables |

**Wall-clock total estimado:** 7-10 días de trabajo paralelo. Buffer 4-7 días para ajustes y defensa.

---

## 2 · Scope concreto de F7

### F7-A · Discovery (HOY, ✅ cerrado)

Outputs en `docs/f7/`:
- ✅ `personas_kpis.md` — 2 personas, 9 dashboards definidos
- 🟡 `branding.md` — placeholder mientras humano sube assets
- ✅ `implementation_plan.md` (este doc)

### F7-B · Design system (Dev T, ~2-3 h)

Entregables:
1. `motoshop-app/web/lib/design/tokens.ts`:
   - `colors` (primary, secondary, neutral 50-900, success, warning, error, info)
   - `spacing` (4, 8, 12, 16, 24, 32, 48, 64)
   - `typography` (heading 1-4, body, small, mono)
   - `radius`, `shadow`, `breakpoints`
2. `motoshop-app/web/tailwind.config.ts` actualizado consumiendo tokens
3. Componentes base en `motoshop-app/web/components/ui/`:
   - `Card.tsx` (deprecar/migrar el de `lib/ui/`)
   - `Stat.tsx` (KPI con valor + delta + sparkline opcional)
   - `Table.tsx` (responsive: tabla desktop, cards stack mobile)
   - `Badge.tsx`
   - `Chart.tsx` (wrapper recharts con `<ResponsiveContainer>` siempre)
   - `Skeleton.tsx` (loading states reusables)
   - `ErrorState.tsx` (error states reusables)
   - `EmptyState.tsx` (lista vacía con mensaje)
4. `motoshop-app/web/components/Logo.tsx` (consume `/public/logo.svg`)
5. `motoshop-app/web/components/Navigation.tsx` adaptable (bottom mobile + sidebar desktop)
6. Stories markdown en `docs/f7/components/<name>.md`

### F7-C · Implementación (Dev T, ~4-6 h)

Entregables:
1. **Home diferenciado por rol** en `motoshop-app/web/app/(authenticated)/page.tsx`:
   - Si `user.role == 'vendedor'`: layout vendedor (búsqueda + alertas + dormidos)
   - Si `user.role in ['admin', 'gerente']`: layout gerente (financiero + decisiones)
2. **Migrar 8 pages existentes** al nuevo sistema:
   - `/dashboards/` (landing gerente)
   - `/dashboards/ventas` (fix bug semántico "tendencia")
   - `/dashboards/inventario`
   - `/dashboards/abc`
   - `/dashboards/dormidos`
   - `/forecast` (si está como page completa)
   - `/alerts`
   - `/acciones`
3. **Crear NUEVA page `/plan-compras`** (decision-oriented gerente)
4. **Backend complementario:**
   - Nuevo endpoint `GET /metrics/sales-trend?periods=6` para tendencia real mensual
   - Nuevo endpoint `GET /metrics/plan-compras` que combine alertas + forecast + ABC + dormidos
5. **Tests E2E Playwright en 3 viewports:**
   - 375px mobile
   - 768px tablet
   - 1280px desktop
6. **Lighthouse audit mobile > 85**, A11y > 90
7. **Deploy + smoke 4G real** desde celular

---

## 3 · V críticas F7 (gates de cierre)

| ID | Verificación | Pass criterion |
|----|--------------|---------------|
| **V-F7-1** | Discovery completo | 3 docs en `docs/f7/` aprobados ✅ |
| **V-F7-2** | Branding subido | `docs/f7/branding/logo.svg` + `colors.md` existen |
| **V-F7-3** | Design system completo | `tokens.ts` + 5+ componentes base + stories |
| **V-F7-4** | Home por rol funcional | Login vendedor → ve búsqueda; login admin → ve financiero |
| **V-F7-5** | 8 pages migradas + 1 nueva | Las 9 pages cargan con nuevo design |
| **V-F7-6** | Bug semántico "tendencia" arreglado | `/ventas` muestra tendencia REAL mensual, no top SKUs disfrazado |
| **V-F7-7** | Mobile-first verificado | Playwright 3 viewports verde + Lighthouse Mobile > 85 |
| **V-F7-8** | A11y AA | Contraste 4.5:1, focus visible, labels en inputs |
| **V-F7-9** | Demo mobile post-F7 mejor | Vos abrís en celular 4G y notás mejora obvia vs pre-F7 |
| **V-F7-10** | Tests pasan | `npm run typecheck` + `npx playwright test` ambos verdes |

**Gate:** V-F7-1 a V-F7-10 PASS → F7 cerrada.

---

## 4 · Dependencias entre sprints

```
F7-A (HOY) ──┬──> F7-B (Dev T, día 2-4)
             │
             └──> Humano sube branding (cuando pueda)
                       │
                       └──> F7-B usa tokens reales (en vez de placeholder)
                              │
                              └──> F7-C (día 4-7)
                                     │
                                     └──> Backend complementario (Dev A: 2 endpoints nuevos)
                                            │
                                            └──> E5 memoria final (Revisor, día 5-7)
                                                   │
                                                   └──> Audit cierre proyecto (Revisor, día 7-10)
```

F7-A no bloquea F6-D-FIX1 (corren en paralelo).
F7-B puede arrancar con tokens placeholder mientras humano sube branding.
F7-C necesita tokens reales (no placeholder) para no requerir re-deploy.

---

## 5 · Riesgos específicos del cronograma

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| R-F7-A1 | Humano no sube branding en 24h | Dev T arranca con placeholder según `branding.md` §"Si NO subís en 24h". Reemplazo posterior. |
| R-F7-A2 | F7-C tarda más de 6h por scope creep | Defender el "NO scope" del plan F7 §2. Cambios nuevos van a F8. |
| R-F7-A3 | Backend endpoints nuevos (sales-trend, plan-compras) atrasan F7-C | Mock en frontend si backend tarda. Reemplazar cuando llegue. |
| R-F7-A4 | Demo gerencia no se puede agendar antes de defensa | Demo a vos mismo o familiar como stand-in. Documentar honestamente. |
| R-F7-A5 | E5 memoria sale mal por falta de capturas | Capturar screenshots durante F7-C continuamente, no al final. |

---

## 6 · Handoffs (a redactar después)

- **F7-B Dev T:** se redacta cuando humano confirme branding subido (o decida ir con placeholder)
- **F7-C Dev T:** se redacta cuando F7-B cierre
- **Backend complementario Dev A:** se redacta junto con F7-C
- **E5 memoria Revisor:** lo hago yo al final

---

## 7 · Aprobación humana

✅ Cronograma 1-2 semanas aceptado  
✅ 9 dashboards definidos (8 migrados + 1 nuevo)  
✅ Home por rol confirmado  
✅ Branding existente — humano sube cuando pueda  
✅ Mobile-first real con breakpoints + touch 44px+  
✅ Bugs semánticos a arreglar identificados

**F7-A Discovery cerrado.** Próximo sprint: F7-B Design system cuando humano confirme branding (o pasen 24h y vamos con placeholder).
