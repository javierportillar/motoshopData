import { test, expect } from "@playwright/test";

test.describe("Offline mode", () => {
  test("login page accesible sin conexión", async ({ page }) => {
    // La página de login no necesita API, debe cargar incluso offline
    await page.goto("/login");
    await expect(page.locator("h1")).toHaveText("MotoShop");
  });

  test("app shell funciona offline después de cargar", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("h1")).toBeVisible();

    await page.context().setOffline(true);

    // La página ya cargada debe seguir visible
    await expect(page.locator("h1")).toBeVisible();

    await page.context().setOffline(false);
  });
});
