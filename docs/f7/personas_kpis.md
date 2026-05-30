# F7-A · Personas + KPIs (Discovery)

- **Fecha:** 2026-05-30 (Sesión 50)
- **Status:** Approved (humano validó las 4 preguntas A2)

---

## 1 · Personas de uso

### P1 · Vendedor en mostrador (mobile-first)

**Contexto:** atendiendo cliente en la tienda con celular en mano. Toque alto, urgencia media-alta.

**Decisiones que toma al abrir la PWA:**
1. **¿Tengo este repuesto?** Búsqueda rápida por nombre/código → resultado con stock por bodega + precio + alternativas si está agotado.
2. **¿Qué le ofrezco/recomiendo?** Saber qué productos en alerta de quiebre vender YA + qué productos dormidos liquidar con descuento + qué tiene mejor rotación.

**Necesidades de UX:**
- Touch targets ≥ 44px obligatorio
- Búsqueda con autofocus al entrar
- Loading states rápidos (la app no puede parecer "pensando")
- Tipografía legible a 30cm de distancia (mínimo 14px body)
- Stock visible sin scroll en ficha SKU

**Lo que NO necesita:**
- Dashboards densos (ventas mensuales, ABC granular, cohortes, drift)
- Exportes / reports
- Configuración

### P2 · Gerente o dueño (desktop-first, también mobile)

**Contexto:** sentado en oficina con monitor 24"+. O en casa por celular revisando KPIs. Densidad de info alta, urgencia baja.

**Decisiones que toma al abrir la PWA:**
1. **¿Cómo va el mes?** Ventas vs mes anterior, ticket promedio, top productos, delta porcentual. **Lo financiero PRIMERO.**
2. **¿Qué tengo que pedir/comprar?** Alertas de quiebre con prioridad, forecast de demanda, ABC para priorizar inversión, dormidos para no recomprar.

**Necesidades de UX:**
- Densidad de información alta (3-4 KPIs por fila en desktop)
- Charts grandes y legibles
- Drill-down de cada KPI a su detalle
- Filtros por período (hoy / semana / mes / trimestre)
- Comparativas (vs mes anterior, vs año pasado cuando haya datos)

**Lo que NO necesita:**
- Búsqueda de productos puntual (raramente)
- Acciones rápidas individuales (las hace el vendedor)

---

## 2 · Home diferenciado por rol

**Decisión:** el `/` después de login NO es la misma pantalla para vendedor y gerente.

### Home vendedor (role = `vendedor`)

Layout mobile-first:
```
┌─────────────────────────────┐
│ [Logo] MotoShop      [Avatar]│
├─────────────────────────────┤
│  🔍 Buscar producto...      │  ← autofocus
│  ___________________________│
├─────────────────────────────┤
│ 🚨 Alertas activas (46)     │  ← card linkeada
│ ┌──────────────────────┐    │
│ │ BATERIA MAGX5L       │    │
│ │ Stock 0 · Vender YA  │    │
│ └──────────────────────┘    │
├─────────────────────────────┤
│ 💤 Dormidos liquidar (8039) │  ← card linkeada
├─────────────────────────────┤
│ 📋 Mis acciones hoy (3)     │
└─────────────────────────────┘
[ Bottom nav: Buscar | Alertas | Acciones | Salir ]
```

### Home gerente (role = `admin` o `gerente`)

Layout desktop-first, responsive a mobile:
```
┌──────────────────────────────────────────────────────────┐
│ [Logo] MotoShop                              [Avatar]   │
├──────────────────────────────────────────────────────────┤
│ Ventas Mayo 2026                                         │
│                                                          │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────┐ │
│ │ $23.5M     │ │ 911 fact.  │ │ $25.8K     │ │ -10.8% │ │
│ │ Ventas mes │ │ Facturas   │ │ Ticket prom│ │ vs ant │ │
│ └────────────┘ └────────────┘ └────────────┘ └────────┘ │
│                                                          │
│ [Gráfico de tendencia mensual REAL (últimos 6 meses)]   │
├──────────────────────────────────────────────────────────┤
│ Decisiones de compra                                     │
│                                                          │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│ │ 🚨 Alertas   │ │ 📈 Forecast  │ │ 📊 ABC       │      │
│ │ 46 activas   │ │ 7d/14d/30d   │ │ A:80% B:15%  │      │
│ └──────────────┘ └──────────────┘ └──────────────┘      │
│                                                          │
│ ┌──────────────┐ ┌──────────────┐                       │
│ │ 💤 Dormidos  │ │ 📦 Inventario│                       │
│ │ 8039 SKUs    │ │ $X.XM valor  │                       │
│ └──────────────┘ └──────────────┘                       │
└──────────────────────────────────────────────────────────┘
[ Sidebar desktop: Home | Ventas | Inventario | ABC | Dormidos | Forecast | Alertas | Acciones ]
```

---

## 3 · KPIs prioritarios

### Por persona

**Vendedor (5 KPIs en home):**
1. Alertas activas (count + 3 top)
2. Productos dormidos para liquidar (count + 3 top con mejor margen)
3. Mis acciones del día (count + última)
4. Búsqueda rápida (no es KPI, pero es el centro de la página)
5. Top 3 productos en rotación A (recomendar)

**Gerente (7 KPIs en home):**
1. Ventas del mes (valor + delta vs mes anterior)
2. Facturas del mes (count + delta)
3. Ticket promedio (valor + delta)
4. Top 5 SKUs del mes (valor + cantidad)
5. Alertas activas (count + prioridad alta)
6. Productos dormidos (count + valor inmovilizado)
7. Valor inventario (BUG actual, fixea F6-D-FIX1)

### Por dashboard

Definición clara de qué muestra cada dashboard (vs el caos actual):

| Dashboard | Audiencia | KPIs principales (3-5) | Visualizaciones |
|-----------|-----------|------------------------|-----------------|
| `/dashboards` (home gerente) | Gerente | 7 KPIs §3 + tendencia mensual | Stat cards + gráfico líneas |
| `/ventas` | Gerente | Ventas mes, ticket, delta, top 10 SKUs | Stat cards + gráfico líneas REAL (no top SKUs disfrazado) + tabla top |
| `/inventario` | Gerente | Stock total, valor inventario, por bodega, dormidos count | Stat cards + tabla bodegas + tabla top dormidos |
| `/abc` | Gerente | % A/B/C en SKUs y en ingresos | Stat cards + gráfico pareto |
| `/dormidos` | Gerente | Count, valor inmovilizado, top 50 | Stat cards + tabla con filtros (días, stock, categoría) |
| `/forecast` | Gerente | Forecast 7d/14d/30d, vs baseline, SKUs cubiertos | Stat cards + tabla por SKU |
| `/alerts` | Vendedor + Gerente | Activas, por urgencia, días hasta quiebre | Tabla con filtros + acción "Gestionar" |
| `/acciones` | Vendedor (sus) + Gerente (todos) | Count del día, por tipo, por usuario | Tabla con filtros |
| `/plan-compras` **NUEVO** | Gerente | Combinación: alertas + forecast + dormidos + ABC priorizado | Tabla decision-oriented con recomendación de cantidad a comprar |

**Total dashboards:** 9 (8 existentes + 1 nuevo)

### NUEVA página: `/plan-compras`

Decision-oriented dashboard que combina lo que hoy está disperso. Para gerente al planear pedido semanal.

Columnas tabla:
- SKU (cod + nombre)
- Stock actual
- Demanda predicha 7d
- Cantidad a comprar (calculada: max(0, demanda_7d - stock_actual))
- Categoría ABC
- Urgencia (de gold.alertas_quiebre)
- ¿Estaba dormido? (proviene de mart_dormidos)
- Top supplier (sugerencia)

Filtros: ABC class, urgencia, supplier, sólo con alerta.

---

## 4 · Bugs semánticos a arreglar en F7-C

Detectados en A1 (audit visual):

1. **Gráfico "Tendencia Mensual" en `/ventas` NO es tendencia.** Es ranking top 5 SKUs. Fixear con tendencia real mensual (necesita endpoint nuevo `/metrics/sales-trend?periods=6`).
2. **`KpiCard` semánticamente abusado en ABC** (usado para mostrar `"A"`, `"B"`, `"C"` como value). Crear `<CategoryCard>` específico.
3. **Loading/error states inconsistentes.** Crear `<Skeleton>` y `<ErrorState>` reusables.
4. **Empty states ausentes.** Mostrar mensaje cuando lista vacía (e.g. "Sin productos dormidos esta semana").

---

## 5 · Lo aprobado por humano (resumen ejecutivo)

✅ Vendedor + gerente como personas igual de importantes  
✅ Vendedor busca + recomienda (mobile-first)  
✅ Gerente revisa financiero primero, después decisiones de compra (desktop-first)  
✅ Home diferenciado por rol  
✅ Nuevo dashboard `/plan-compras` (decision-oriented)  
✅ Arreglar bug semántico "tendencia" en `/ventas`  
✅ Branding existente (humano sube logo + colores a `docs/f7/branding/`)  
✅ Mobile-first real con breakpoints  
✅ Navegación adaptable: bottom nav mobile + sidebar desktop  
✅ Timeline 1-2 semanas (antes de defensa académica)
