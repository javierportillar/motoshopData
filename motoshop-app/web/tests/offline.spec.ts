import { test, expect } from "@playwright/test";

test.describe("Offline mode", () => {
  test("PWA funciona después de cargar (modo avión)", async ({ page }) => {
    // Este test requiere PWA instalada y datos cacheados
    test.skip(!process.env.API_URL, "Requires real API + PWA");

    await page.goto("/products");
    await expect(page.locator("h1")).toHaveText("Buscar");

    // Simular offline
    await page.context().setOffline(true);

    // La página debe seguir visible (app shell cacheada)
    await expect(page.locator("h1")).toBeVisible();

    // Restaurar online
    await page.context().setOffline(false);
  });
});
