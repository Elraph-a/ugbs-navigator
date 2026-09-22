/**
 * Check conversation turns through the real interface.
 *
 *   node scripts/greeting-check.mjs
 *
 * Types into the composer the way a student would, rather than using ?q=, and
 * asserts on what is rendered: a greeting must read as a message, with no
 * procedure card, no Verified badge and no "Copy steps" — and a greeting
 * attached to a real question must still produce the procedure.
 */

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const BASE = "http://localhost:3000";
const OUT = "../.impeccable/review";

const failures = [];
const errors = [];

function check(label, ok, detail = "") {
  console.log(`  ${ok ? "pass" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures.push(label);
}

async function send(page, text) {
  const box = page.getByPlaceholder(/Ask/);
  await box.fill(text);
  await box.press("Enter");
}

/* `waitFor` on text resolves the moment the node enters the DOM — while the
   entrance animation still has it at ~0.2 opacity. A screenshot taken then
   comes out blank and looks like a rendering bug that is not there. */
async function settle(page) {
  await page.waitForFunction(() =>
    [...document.querySelectorAll(".rise, .pop, .slip")].every(
      (el) => getComputedStyle(el).opacity === "1",
    ),
  );
}

const run = async () => {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto(BASE, { waitUntil: "networkidle" });

  /* ------------------------------------------------------------ hello ---- */
  console.log("\n'hello'");
  await send(page, "hello");
  await page.getByText(/I answer questions about University of Ghana/).waitFor({ timeout: 30_000 });
  await settle(page);

  check("reply is the greeting, not a refusal",
    (await page.getByText(/could not find a published source/i).count()) === 0);
  check("no Verified badge", (await page.getByText("Verified", { exact: true }).count()) === 0);
  check("no procedure card header", (await page.getByText("General enquiry").count()) === 0);
  check("no Copy steps footer", (await page.getByText(/Copy steps/).count()) === 0);
  check("example questions render as a list",
    (await page.locator("ul li").filter({ hasText: /transcript/i }).count()) > 0);
  await page.screenshot({ path: `${OUT}/greet-hello.png` });

  /* ------------------------------------------------- what can you do ---- */
  console.log("\n'what can you do?'");
  await send(page, "what can you do?");
  await page.getByText(/enquiry assistant for UGBS students/).waitFor({ timeout: 30_000 });
  await settle(page);
  check("capability reply renders", true);
  check("still no Verified badge", (await page.getByText("Verified", { exact: true }).count()) === 0);
  await page.screenshot({ path: `${OUT}/greet-capability.png` });

  /* ---------------------------------------- greeting + real question ---- */
  console.log("\n'hi, how do I get a transcript?'");
  await send(page, "hi, how do I get a transcript?");
  await page.getByText(/Copy steps/).first().waitFor({ timeout: 90_000 });
  await settle(page);
  check("treated as an enquiry: procedure card appears",
    (await page.getByText("Verified", { exact: true }).count()) > 0);
  check("office card appears", (await page.getByText(/Go here/).count()) > 0);
  await page.screenshot({ path: `${OUT}/greet-then-enquiry.png` });

  await browser.close();

  console.log("\n" + "-".repeat(56));
  if (errors.length) {
    console.log(`${errors.length} browser error(s):`);
    for (const e of errors) console.log("  " + e);
  }
  console.log(failures.length ? `${failures.length} check(s) FAILED` : "All checks passed.");
  process.exit(failures.length || errors.length ? 1 : 0);
};

run().catch((error) => {
  console.error("\nFAILED:", error.message);
  process.exit(1);
});
