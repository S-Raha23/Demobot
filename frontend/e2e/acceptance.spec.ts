import { expect, test } from "@playwright/test";

// Fix-0 acceptance (docs/11): Home, one run page, Try-it for every skill, and Costs.
// Screenshots go to frontend/test-results/ for review. Runs against the Vite dev server
// (backend on :8000 via `make api`); replay/Try-it are free (no model calls).
const shot = (name: string) => ({ path: `test-results/${name}.png`, fullPage: false });

test("acceptance: home, run page, costs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Show it/ })).toBeVisible();
  await expect(page.getByTestId("skills")).toBeVisible();
  await page.screenshot(shot("a1-home"));

  await page.getByTestId("watch-best").click();
  await expect(page.getByTestId("stepper")).toBeVisible();
  // at 1366px the stepper must fit without horizontal scrolling
  const overflow = await page.getByTestId("stepper").evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot(shot("a2-run-page"));

  await page.goto("/costs");
  await expect(page.getByRole("heading", { name: /What it costs/ })).toBeVisible();
  await page.screenshot(shot("a3-costs"));
});

test("acceptance: try-it for every skill card", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("skills")).toBeVisible();
  const tries = page.locator('[aria-label^="Try it:"]');
  const n = await tries.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    await tries.nth(i).click();
    await expect(page.getByTestId("try-run")).toBeVisible();
    await page.screenshot(shot(`a4-try-it-${i}`));
    await page.goto("/");
    await expect(page.getByTestId("skills")).toBeVisible();
  }
});
