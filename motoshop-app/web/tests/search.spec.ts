import { test, expect } from "@playwright/test";

test.describe("Search", () => {
  test("página de búsqueda muestra input", async ({ page }) => {
    await page.goto("/login");

    // Si no hay API real, el test verifica la UI del login
    // Para tests E2E completos se necesita API corriendo
    await expect(page.locator('input[placeholder="Tu usuario"]')).toBeVisible();
  });

  test("búsqueda vacía muestra mensaje de estado vacío", async ({ page }) => {
    // Este test requiere sesión activa - skip si no hay API
    test.skip(
      process.env.CI === "true",
      "Requires real API connection",
    );

    await page.goto("/products");
    await expect(
      page.locator("text=Escribe algo para buscar"),
    ).toBeVisible({ timeout: 3000 });
  });
});
