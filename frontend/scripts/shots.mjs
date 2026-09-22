/**
 * Screenshot the running app and report any browser-side errors.
 *
 *   node scripts/shots.mjs
 *
 * Headless Edge could not capture the answering state at all: it exits without
 * writing once the SSE stream is open. Playwright waits on real selectors, so it
 * captures mid-stream and settled states, and — the part that matters more —
 * it surfaces console and page errors that a screenshot alone would hide.
 */

import { chromium, devices } from "playwright";
import { mkdir } from "node:fs/promises";

const BASE = "http://localhost:3000";
const OUT = "../.impeccable/review";

const TRANSCRIPT = "How do I request an official transcript?";
const COMPLEX =
  "I am a UGBS graduate student, I need my transcript urgently and I graduated in 1994";
const REFUSAL = "What will the 2027/2028 MBA fee be?";

const problems = [];

function watch(page, label) {
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`[${label}] console: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`[${label}] pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    // Aborted navigations are normal when a page is closed mid-flight.
    if (!failure.includes("ABORTED")) {
      problems.push(`[${label}] requestfailed: ${request.url()} ${failure}`);
    }
  });
}

/* The conversation scrolls inside its own element, so fullPage captures only the
   viewport. Shots are viewport-sized by design — that is what a person sees —
   and `scrollTo` takes a second frame of the same answer further down. */
async function shoot(page, name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log(`  captured ${name}`);
}

async function scrollTo(page, ratio) {
  await page.evaluate((r) => {
    const el = document.querySelector("[data-scroller]");
    if (el) el.scrollTop = (el.scrollHeight - el.clientHeight) * r;
  }, ratio);
  await page.waitForTimeout(500);
}

async function ask(page, question) {
  await page.goto(`${BASE}/?q=${encodeURIComponent(question)}`, {
    waitUntil: "domcontentloaded",
  });
}

async function settled(page) {
  // The footer only renders once the run finishes, so it is the honest signal
  // that the stream closed rather than a fixed wait.
  await page.getByText(/Copy steps/).first().waitFor({ timeout: 90_000 });
  // Entrance animations are still running at that moment; capturing now records
  // half-faded cards and reads as a contrast bug that is not there.
  await page.waitForTimeout(700);
}

const run = async () => {
  await mkdir(OUT, { recursive: true });

  const browser = await chromium.launch();

  /* ---------------------------------------------------------- desktop ---- */
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await desktop.newPage();
  watch(page, "desktop");

  console.log("\ndesktop");

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.getByText(/Which office handles it/).waitFor();
  await page.waitForTimeout(600);
  await shoot(page, "pw-welcome");

  // Mid-stream: catch the agent while it is still working.
  await ask(page, COMPLEX);
  // "Planning" lands as a completed step, by which point a search is in flight
  // and the header is showing it.
  await page.getByText(/Planning/).first().waitFor({ timeout: 60_000 });
  await page.waitForTimeout(300);
  await shoot(page, "pw-streaming");

  await settled(page);
  await shoot(page, "pw-answer-complex");
  await scrollTo(page, 0.55);
  await shoot(page, "pw-answer-complex-mid");
  await scrollTo(page, 1);
  await shoot(page, "pw-answer-complex-end");

  await ask(page, TRANSCRIPT);
  await settled(page);
  await shoot(page, "pw-answer-transcript");

  // The cedi sign is the one glyph a wrong font silently mangles, and it sits on
  // every transcript fee. Assert the DOM text, not the pixels.
  const feeText = await page.getByText(/GH/).first().innerText();
  const cedi = feeText.includes("₵");
  console.log(`\n  fee cell reads ${JSON.stringify(feeText)} -> cedi sign ${cedi ? "present" : "MISSING"}`);
  if (!cedi) problems.push(`fee text lost the cedi sign: ${feeText}`);

  await scrollTo(page, 1);
  await shoot(page, "pw-answer-transcript-end");

  // Sources are collapsed by default; open one so the citation design is visible.
  await page.getByRole("button", { name: /source/i }).first().click();
  await page.waitForTimeout(500);
  await shoot(page, "pw-answer-sources");

  await ask(page, REFUSAL);
  await page.getByText(/could not find a published source/i).waitFor({ timeout: 90_000 });
  await page.waitForTimeout(600);
  await shoot(page, "pw-refusal");

  await page.goto(`${BASE}/admin`, { waitUntil: "networkidle" });
  await page.getByText(/What to publish next/).waitFor({ timeout: 60_000 });
  await page.waitForTimeout(700);
  await shoot(page, "pw-admin");

  /* ----------------------------------------------------------- mobile ---- */
  console.log("\nmobile (Pixel 7 viewport)");

  const mobile = await browser.newContext({
    ...devices["Pixel 7"],
  });
  const small = await mobile.newPage();
  watch(small, "mobile");

  await small.goto(BASE, { waitUntil: "networkidle" });
  await small.getByText(/Which office handles it/).waitFor();
  await small.waitForTimeout(600);
  await shoot(small, "pw-mobile-welcome");

  await ask(small, TRANSCRIPT);
  await settled(small);
  await shoot(small, "pw-mobile-answer");
  await scrollTo(small, 1);
  await shoot(small, "pw-mobile-answer-end");

  // Horizontal overflow is the failure that matters on a phone.
  const overflow = await small.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth,
  }));
  console.log(
    `\n  document width ${overflow.doc}px vs viewport ${overflow.win}px -> ` +
      (overflow.doc > overflow.win + 1 ? "HORIZONTAL OVERFLOW" : "no overflow"),
  );
  if (overflow.doc > overflow.win + 1) {
    problems.push(`mobile: page scrolls horizontally (${overflow.doc} > ${overflow.win})`);
  }

  await small.goto(`${BASE}/admin`, { waitUntil: "networkidle" });
  await small.getByText(/What to publish next/).waitFor({ timeout: 60_000 });
  await shoot(small, "pw-mobile-admin");

  await browser.close();

  console.log("\n" + "-".repeat(58));
  if (problems.length === 0) {
    console.log("No console errors, page errors or failed requests.");
  } else {
    console.log(`${problems.length} problem(s):\n`);
    for (const problem of problems) console.log("  " + problem);
  }
};

run().catch((error) => {
  console.error("\nFAILED:", error.message);
  if (problems.length) {
    console.error("\nbrowser problems seen before the failure:");
    for (const problem of problems) console.error("  " + problem);
  }
  process.exit(1);
});
