import { test, expect, type Page, type Route } from "@playwright/test";

// ── Helpers ───────────────────────────────────────────────────────────────

const MOCK_ALERTS = {
  alerts: [
    { sku: "MOTS1297", nom_producto: "ACEITE 20W50 MOTUL 1L", stock_actual: 5, demanda_predicha: 12.5, dias_hasta_quiebre: 2, urgencia: "alta" },
    { sku: "MOTS0412", nom_producto: "FILTRO ACEITE YAMAHA YBR125", stock_actual: 3, demanda_predicha: 8.0, dias_hasta_quiebre: 4, urgencia: "media" },
    { sku: "MOTS0834", nom_producto: "PASTILLAS FRENO DELANTERAS", stock_actual: 1, demanda_predicha: 15.0, dias_hasta_quiebre: 0, urgencia: "alta" },
  ],
  total: 3,
  timestamp: "2026-05-30T12:00:00",
};

async function mockEndpoints(page: Page) {
  await page.route("**/api/alerts/stockout*", (route: Route) =>
    route.fulfill({ json: MOCK_ALERTS }),
  );
  await page.route("**/api/alerts/*/action", (route: Route) =>
    route.fulfill({ status: 201, json: { id: 1, sku: "MOTS1297", action_type: "ordered", user_id: "admin", created_at: new Date().toISOString() } }),
  );
  await page.route("**/api/alerts/actions/me*", (route: Route) =>
    route.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/api/health/data-freshness", (route: Route) =>
    route.fulfill({ json: { status: "OK", lag_hours: 2, last_manifest: "test.parquet" } }),
  );
}

async function setAuthRole(page: Page, role: string) {
  await page.evaluate((r: string) => {
    (window as { __setAuthRole?: (role: string) => void }).__setAuthRole?.(r);
  }, role);
}

async function loginAndSetRole(page: Page, role: string) {
  // Bypass middleware
  await page.context().addCookies([
    { name: "motoshop_token", value: "test", domain: "localhost", path: "/" },
  ]);
}

// ── Tests ─────────────────────────────────────────────────────────────────

test.describe("Alert Action UI", () => {
  test.beforeEach(async ({ page }) => {
    await mockEndpoints(page);
  });

  test("admin ve botón Gestionar y puede marcar alerta como ordered", async ({ page }) => {
    await loginAndSetRole(page, "admin");

    await page.goto("/alerts");
    await expect(page.getByText("MOTS1297")).toBeVisible({ timeout: 10000 });

    // Inyectar role después de que la página cargue
    await setAuthRole(page, "admin");
    await expect(page.getByText("Gestionar").first()).toBeVisible({ timeout: 5000 });

    // Abrir modal
    await page.getByText("Gestionar").first().click();
    await expect(page.getByText("Gestionar alerta")).toBeVisible();
    await expect(page.getByText("Cantidad a pedir")).toBeVisible();

    // Llenar y submit (el botón submit NO tiene role="tab", a diferencia del tab)
    await page.fill("input[type=number]", "50");
    await page.click('button:not([role="tab"]):has-text("Pedir")');
    await expect(page.getByText("✓ Guardado")).toBeVisible({ timeout: 5000 });
  });

  test("admin puede descartar alerta", async ({ page }) => {
    await loginAndSetRole(page, "admin");

    await page.goto("/alerts");
    await expect(page.getByText("MOTS1297")).toBeVisible({ timeout: 10000 });
    await setAuthRole(page, "admin");
    await expect(page.getByText("Gestionar").first()).toBeVisible({ timeout: 5000 });

    await page.getByText("Gestionar").first().click();
    await expect(page.getByText("Gestionar alerta")).toBeVisible();

    // Tab Descartar
    await page.getByText("Descartar").click();
    await expect(page.getByText("Motivo")).toBeVisible();
    await page.fill("textarea", "Ya hay pedido en tránsito");
    await page.click('button:not([role="tab"]):has-text("Descartar")');
    await expect(page.getByText("✓ Guardado")).toBeVisible({ timeout: 5000 });
  });

  test("vendedor NO ve botón Gestionar", async ({ page }) => {
    await loginAndSetRole(page, "vendedor");

    await page.goto("/alerts");
    await expect(page.getByText("MOTS1297")).toBeVisible({ timeout: 10000 });
    await setAuthRole(page, "vendedor");

    // El botón no debe existir
    await expect(page.getByText("Gestionar")).not.toBeVisible();
  });

  test("validación frontend: ordered requiere cantidad", async ({ page }) => {
    await loginAndSetRole(page, "admin");

    await page.goto("/alerts");
    await expect(page.getByText("MOTS1297")).toBeVisible({ timeout: 10000 });
    await setAuthRole(page, "admin");
    await expect(page.getByText("Gestionar").first()).toBeVisible({ timeout: 5000 });

    await page.getByText("Gestionar").first().click();
    await expect(page.getByText("Gestionar alerta")).toBeVisible();

    // Submit sin cantidad (el botón submit NO tiene role="tab")
    await page.click('button:not([role="tab"]):has-text("Pedir")');
    await expect(page.getByText("Requerido")).toBeVisible();
  });

  test("acciones page carga sin errores", async ({ page }) => {
    await loginAndSetRole(page, "admin");

    // Mock actions endpoint con datos
    await page.route("**/api/alerts/actions/me*", (route: Route) =>
      route.fulfill({
        json: {
          items: [
            { id: 1, alert_id: "MOTS1297", sku: "MOTS1297", action_type: "ordered", quantity: 50, created_at: new Date().toISOString() },
          ],
          total: 1,
        },
      }),
    );

    await page.goto("/acciones");
    await expect(page.getByText("Mis acciones del día")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("MOTS1297")).toBeVisible();
  });
});
