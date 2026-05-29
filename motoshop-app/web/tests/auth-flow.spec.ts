import { test, expect } from "@playwright/test";

test.describe("Auth flow", () => {
  test("redirige a /login si no hay sesión", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login muestra formulario", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("h1")).toHaveText("MotoShop");
    await expect(page.locator('input[placeholder="Tu usuario"]')).toBeVisible();
    await expect(
      page.locator('input[placeholder="Tu contraseña"]'),
    ).toBeVisible();
  });

  test("login con credenciales inválidas muestra error", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[placeholder="Tu usuario"]', "baduser");
    await page.fill('input[placeholder="Tu contraseña"]', "badpass");
    await page.click('button[type="submit"]');

    await expect(page.locator(".text-error, [class*='text-red']")).toBeVisible({
      timeout: 5000,
    });
  });

  test("campos vacíos muestran error de validación", async ({ page }) => {
    await page.goto("/login");
    await page.click('button[type="submit"]');

    await expect(page.locator("text=Requerido")).toBeVisible();
    await expect(page.locator("text=Requerida")).toBeVisible();
  });
});
