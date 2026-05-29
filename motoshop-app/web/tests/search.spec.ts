import { test, expect } from "@playwright/test";

test.describe("Search", () => {
  test("página de búsqueda redirige a login sin sesión", async ({ page }) => {
    await page.goto("/products");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login carga formulario correctamente", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator('input[placeholder="Tu usuario"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Tu contraseña"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });
});
