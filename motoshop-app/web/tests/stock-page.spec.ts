import { test, expect } from "@playwright/test";

test.describe("SKU page", () => {
  test("redirige a /login sin sesión", async ({ page }) => {
    await page.goto("/products/ACEITE001");
    await expect(page).toHaveURL(/\/login/);
  });

  test("página de login es accesible desde ruta protegida", async ({ page }) => {
    await page.goto("/products/ACEITE001");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator("h1")).toHaveText("MotoShop");
  });
});
