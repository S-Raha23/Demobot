// Records "takes" of the DemoBot UI for scripts/record_demo.py: CDP screencast frames (JPEG, much
// sharper than Playwright's built-in 1 Mbps video) plus the wall times at which named marks first
// hold (a stage's status in the stepper, or a text on the page).
//
//   node scripts/record_demo.cjs <plan.json> <out_dir>
//
// plan: {base, width, height, takes: [{name, url, marks: [{name, stage, status} | {name, text} |
//        {name, selector}], actions: [{click} | {wait} | {waitMark}], end: {mark, after_s}, max_s,
//        rects: {name: selector}}]}
// out:  <out_dir>/<take>/NNNNNN.jpg, frames.ffconcat (per-frame durations), marks.json (seconds,
//       plus _length and the _rects of the named elements)
const fs = require("fs");
const path = require("path");
const { chromium } = require(require.resolve("playwright", { paths: [path.join(__dirname, "..", "frontend")] }));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function recordTake(browser, plan, take, outDir) {
  const dir = path.join(outDir, take.name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const page = await browser.newPage({ viewport: { width: plan.width, height: plan.height } });
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on("Page.screencastFrame", async (f) => {
    const file = `${String(frames.length).padStart(6, "0")}.jpg`;
    frames.push({ ts: f.metadata.timestamp, file });
    fs.writeFileSync(path.join(dir, file), Buffer.from(f.data, "base64"));
    await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await page.goto(plan.base + take.url);
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: plan.width, maxHeight: plan.height });
  const t0 = Date.now() / 1000;
  const marks = {};
  let polling = true;
  const poll = (async () => {
    while (polling) {
      const held = await page
        .evaluate((ms) => ms.map((m) => (m.stage
          ? document.querySelector(`[data-stage="${m.stage}"]`)?.dataset.status === m.status
          : m.selector ? Boolean(document.querySelector(m.selector))
          : document.body.innerText.includes(m.text))), take.marks)
        .catch(() => []);
      held.forEach((h, i) => {
        const name = take.marks[i].name;
        if (h && !(name in marks)) marks[name] = Date.now() / 1000;
      });
      await sleep(100);
    }
  })();
  const deadline = t0 + (take.max_s ?? 240);
  const waitMark = async (name) => {
    while (!(name in marks) && Date.now() / 1000 < deadline) await sleep(100);
  };
  for (const a of take.actions ?? []) {
    if (a.wait) await sleep(a.wait);
    if (a.waitMark) await waitMark(a.waitMark);
    if (a.click) await page.click(a.click, { timeout: 15000 });
  }
  if (take.end?.mark) await waitMark(take.end.mark);
  await sleep((take.end?.after_s ?? 0) * 1000);
  polling = false;
  await poll;
  const rects = {};
  for (const [name, sel] of Object.entries(take.rects ?? {})) rects[name] = await page.locator(sel).first().boundingBox();
  await cdp.send("Page.stopScreencast");
  await page.close();
  if (!frames.length) throw new Error(`no frames recorded for ${take.name}`);
  // the first frame's time is the take's zero; each frame lasts until the next one arrives
  const first = frames[0].ts;
  const lines = ["ffconcat version 1.0"];
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].ts : f.ts + 0.1;
    lines.push(`file '${f.file}'`, `duration ${Math.max(0.001, next - f.ts).toFixed(3)}`);
  });
  lines.push(`file '${frames[frames.length - 1].file}'`);
  fs.writeFileSync(path.join(dir, "frames.ffconcat"), lines.join("\n") + "\n");
  const rel = Object.fromEntries(Object.entries(marks).map(([k, v]) => [k, +(v - first).toFixed(2)]));
  rel._length = +(frames[frames.length - 1].ts - first + 0.1).toFixed(2);
  rel._rects = rects;
  fs.writeFileSync(path.join(dir, "marks.json"), JSON.stringify(rel, null, 1));
  console.log(`${take.name}: ${frames.length} frames, ${rel._length}s, marks ${JSON.stringify(rel)}`);
}

(async () => {
  const [planPath, outDir] = process.argv.slice(2);
  const plan = JSON.parse(fs.readFileSync(planPath, "utf8"));
  const browser = await chromium.launch({
    executablePath: process.env.PW_CHROME || undefined,
    headless: true,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
  });
  try {
    for (const take of plan.takes) await recordTake(browser, plan, take, outDir);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
