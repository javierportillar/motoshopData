import { test, expect } from "@playwright/test";

test.describe("Dashboards", () => {
  test("redirige a /login sin sesión", async ({ page }) => {
    await page.goto("/dashboards");
    await expect(page).toHaveURL(/\/login/);
  });

  test("subrutas también redirigen sin sesión", async ({ page }) => {
    await page.goto("/dashboards/ventas");
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/dashboards/inventario");
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/dashboards/abc");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login protegido para dashboards", async ({ page }) => {
    await page.goto("/dashboards");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator("h1")).toHaveText("MotoShop");
  });
});
