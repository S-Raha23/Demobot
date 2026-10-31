import { expect, test } from "@playwright/test";

// Home -> open the best run's replay -> skip to result -> Try it -> Run. Screenshots at
// 1920×1080 go to frontend/test-results/.
const shot = (name: string) => ({ path: `test-results/${name}.png`, fullPage: false });

test("home -> replay -> skip to result -> try it", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Show it/ })).toBeVisible();
  await expect(page.getByTestId("skills")).toBeVisible();
  await page.waitForTimeout(1500);
  await page.screenshot(shot("01-home"));

  await page.getByTestId("watch-best").click();
  await expect(page.getByTestId("stepper")).toBeVisible();
  await page.waitForTimeout(6000);
  await page.screenshot(shot("02-run-replaying"));

  await page.getByTestId("skip").click();
  await expect(page.getByText("Skill learned")).toBeVisible();
  await page.waitForTimeout(4000);
  await page.screenshot(shot("03-run-result"));

  await page.getByRole("link", { name: /Try it yourself/ }).click();
  await expect(page.getByTestId("try-run")).toBeVisible();
  await page.waitForTimeout(3000);
  await page.screenshot(shot("04-try-it"));
  await page.getByTestId("try-run").click();
  await expect(page.getByText(/program v\d+ · sim/)).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(4000);
  await page.screenshot(shot("05-try-it-running"));
});
