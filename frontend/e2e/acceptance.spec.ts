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
  test.setTimeout(600_000); // ~11 skills x WebGL load each; the default 120 s cannot cover them
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("skills")).toBeVisible();
  // collect the Try-it URLs first: clicking through the live DOM re-renders the grid
  // (cards below the fold never become "stable" for a direct click)
  const hrefs = await page.locator('[aria-label^="Try it:"]').evaluateAll((els) =>
    els.map((e) => (e as HTMLAnchorElement).getAttribute("href")).filter((h): h is string => Boolean(h)),
  );
  expect(hrefs.length).toBeGreaterThan(0);
  for (let i = 0; i < hrefs.length; i++) {
    await page.goto(hrefs[i], { waitUntil: "commit" });
    await expect(page.getByTestId("try-run")).toBeVisible({ timeout: 30_000 });
    await page.screenshot(shot(`a4-try-it-${i}`));
  }
});
