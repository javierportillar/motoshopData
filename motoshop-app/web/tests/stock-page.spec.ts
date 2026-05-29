import { test, expect } from "@playwright/test";

test.describe("SKU page", () => {
  test("redirige a /login sin sesión", async ({ page }) => {
    await page.goto("/products/ACEITE001");
    await expect(page).toHaveURL(/\/login/);
  });

  test("página de producto muestra botón volver", async ({ page }) => {
    // Este test requiere API real - skip si no hay conexión
    test.skip(!process.env.API_URL, "Requires real API");

    await page.goto("/products/ACEITE001");
    await expect(page.locator("text=Volver")).toBeVisible({ timeout: 5000 });
  });
});
