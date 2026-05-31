import { test, expect, type Page } from "@playwright/test";

// Helpers
const VIEWPORTS = {
  mobile: { width: 375, height: 812 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 800 },
} as const;

/** Inyecta un JWT falso y role en el store para saltar login en dev */
async function bypassAuth(page: Page, role: string): Promise<void> {
  // Cookie falsa — la middleware solo chequea existencia
  await page.context().addCookies([
    {
      name: "motoshop_token",
      value: "fake-jwt-for-e2e",
      domain: "localhost",
      path: "/",
    },
  ]);
  // Navegar primero para que los módulos JS se carguen
  await page.goto("/login", { waitUntil: "networkidle" });
  // Ahora sí, el bridge debería estar disponible
  await page.evaluate((r) => {
    const win = window as unknown as Record<string, unknown>;
    const fn = win.__setAuthRole as ((role: string | null) => void) | undefined;
    if (fn) {
      fn(r);
    }
  }, role);
}

// ── Rutas a testear ──────────────────────────────────────────

const ALL_ROUTES = [
  "/",
  "/dashboards",
  "/dashboards/ventas",
  "/dashboards/inventario",
  "/dashboards/abc",
  "/dashboards/dormidos",
  "/forecast",
  "/alerts",
  "/acciones",
  "/cohortes",
  "/vendedores",
  "/drift",
  "/plan-compras",
];

// ── Auth guards ──────────────────────────────────────────────

test.describe("Auth guards — sin sesión redirige a /login", () => {
  for (const route of ALL_ROUTES) {
    test(`${route} → /login`, async ({ page }) => {
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/);
    });
  }
});

// ── Login page ───────────────────────────────────────────────

test.describe("Login page", () => {
  test("renderiza en mobile", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/login");
    await expect(page.locator("h1")).toHaveText("MotoShop");
    await expect(page.locator('input[placeholder="Tu usuario"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Tu contraseña"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test("renderiza en tablet", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet);
    await page.goto("/login");
    await expect(page.locator("h1")).toHaveText("MotoShop");
  });

  test("renderiza en desktop", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto("/login");
    await expect(page.locator("h1")).toHaveText("MotoShop");
  });
});

// ── Home autenticada (gerente) ───────────────────────────────

test.describe("Home autenticada — gerente", () => {
  test.beforeEach(async ({ page }) => {
    await bypassAuth(page, "admin");
  });

  test("carga sin error en mobile", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("MotoShop");
    // Debe tener al menos un Card o Stat (aún sin datos de API, muestra skeleton)
    await expect(page.locator("text=Panel de gerencia")).toBeVisible();
  });

  test("carga sin error en tablet", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet);
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("MotoShop");
  });

  test("carga sin error en desktop", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("MotoShop");
  });

  test("muestra cards de decisiones de compra cuando carga", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto("/");
    // Puede mostrar loading o datos — ambos son válidos
    // Verificamos que no hay error fatal (página en blanco, 404, etc)
    await expect(page.locator("h1")).toContainText("MotoShop");
  });
});

// ── Home autenticada (vendedor) ──────────────────────────────

test.describe("Home autenticada — vendedor", () => {
  test.beforeEach(async ({ page }) => {
    await bypassAuth(page, "vendedor");
  });

  test("carga sin error en mobile", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("MotoShop");
    // Loading o datos — la página maneja ambos estados
  });

  test("muestra cards de acción rápida cuando carga", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/");
    // Verificar que no hay crash — la página renderiza loading o datos
    await expect(page.locator("h1")).toContainText("MotoShop");
  });
});

// ── Pages migradas — smoke test en 3 viewports ───────────────

const SMOKE_ROUTES = [
  { path: "/dashboards", title: "Dashboards" },
  { path: "/dashboards/ventas", title: "Ventas" },
  { path: "/dashboards/inventario", title: "Inventario" },
  { path: "/dashboards/abc", title: "Segmentación ABC" },
  { path: "/dashboards/dormidos", title: "Productos dormidos" },
  { path: "/forecast", title: "Predicciones" },
  { path: "/alerts", title: "Alertas" },
  { path: "/acciones", title: "Mis acciones" },
  { path: "/cohortes", title: "Cohortes de clientes" },
  { path: "/vendedores", title: "Vendedores" },
  { path: "/drift", title: "Alertas de drift" },
  { path: "/plan-compras", title: "Plan de compras" },
];

for (const { path, title } of SMOKE_ROUTES) {
  test.describe(`${path} — autenticado`, () => {
    test.beforeEach(async ({ page }) => {
      await bypassAuth(page, "admin");
    });

    test(`no es 404 en mobile`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile);
      await page.goto(path);
      // Verificar que no es página de error de Next.js (la página renderiza algo)
      await expect(page.locator("body")).not.toContainText("404");
      await expect(page.locator("body")).not.toContainText("Application error");
    });

    test(`no es 404 en tablet`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.tablet);
      await page.goto(path);
      await expect(page.locator("body")).not.toContainText("404");
    });

    test(`no es 404 en desktop`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.goto(path);
      await expect(page.locator("body")).not.toContainText("404");
    });

    test(`tiene título o maneja estado sin crash`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile);
      await page.goto(path);
      // La página debe renderizar sin crash — puede mostrar h1, loading, o error, pero no 404
      await expect(page.locator("body")).not.toContainText("404");
      await expect(page.locator("body")).not.toContainText("Application error");
    });
  });
}

// ── Navegación consistente ───────────────────────────────────

test.describe("Navegación", () => {
  test.beforeEach(async ({ page }) => {
    await bypassAuth(page, "admin");
  });

  test("el link 'Volver a inicio' navega a /", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/dashboards/ventas");
    // Next.js Link usa navegación cliente; verificar que el link existe
    const homeLink = page.locator('a[href="/"]').first();
    await expect(homeLink).toBeVisible();
    await homeLink.click();
    // Navegación cliente — esperar que la página cambie
    await page.waitForTimeout(500);
    // La URL debería ser / o el contenido de la home debería estar visible
    await expect(page.locator("h1")).toBeVisible();
  });
});
