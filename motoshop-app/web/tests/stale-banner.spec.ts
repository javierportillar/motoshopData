import { test, expect } from "@playwright/test";

const STALE_RESPONSE = {
  status: "STALE",
  lag_hours: 48,
  last_manifest: "2024-01-01.parquet",
};

const FRESH_RESPONSE = {
  status: "OK",
  lag_hours: 2,
  last_manifest: "2026-05-30.parquet",
};

test.describe("StaleDataBanner", () => {
  test.beforeEach(async ({ page }) => {
    // La middleware verifica motoshop_token; cualquier valor no vacío pasa
    await page.context().addCookies([
      { name: "motoshop_token", value: "test-token", domain: "localhost", path: "/" },
    ]);
  });

  test("forecast page muestra banner cuando datos tienen 48h de lag", async ({ page }) => {
    await page.route("**/api/health/data-freshness", (route) =>
      route.fulfill({ json: STALE_RESPONSE }),
    );

    await page.goto("/forecast");
    await expect(page.getByTestId("stale-banner")).toBeVisible();
    await expect(page.getByTestId("stale-banner")).toContainText("hace 2d");
  });

  test("alerts page muestra banner cuando datos tienen 48h de lag", async ({ page }) => {
    await page.route("**/api/health/data-freshness", (route) =>
      route.fulfill({ json: STALE_RESPONSE }),
    );

    await page.goto("/alerts");
    await expect(page.getByTestId("stale-banner")).toBeVisible();
    await expect(page.getByTestId("stale-banner")).toContainText("hace 2d");
  });

  test("no muestra banner cuando datos están frescos (lag 2h)", async ({ page }) => {
    await page.route("**/api/health/data-freshness", (route) =>
      route.fulfill({ json: FRESH_RESPONSE }),
    );

    await page.goto("/forecast");
    await expect(page.getByTestId("stale-banner")).not.toBeVisible();
  });

  test("banner de error cuando health endpoint falla", async ({ page }) => {
    await page.route("**/api/health/data-freshness", (route) =>
      route.abort("connectionrefused"),
    );

    await page.goto("/forecast");
    await expect(page.getByTestId("stale-banner")).toBeVisible();
    await expect(page.getByTestId("stale-banner")).toContainText("No se pudo verificar");
  });
});
