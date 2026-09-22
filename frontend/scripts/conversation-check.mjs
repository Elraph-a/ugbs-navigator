/**
 * Hold a real conversation through the interface and check it behaves.
 *
 *   node scripts/conversation-check.mjs
 *
 * Types into the composer the way a student would. Checks what matters for a
 * conversational agent: that the reply streams, that follow-ups with no nouns
 * in them are understood from context, that facts still come from the
 * documents, and that off-topic questions are declined.
 */

import { chromium, devices } from "playwright";
import { mkdir } from "node:fs/promises";

const BASE = "http://localhost:3000";
const OUT = "../.impeccable/review";

const failures = [];
const errors = [];

function check(label, ok, detail = "") {
  console.log(`  ${ok ? "pass" : "FAIL"}  ${label}${detail ? `  — ${detail}` : ""}`);
  if (!ok) failures.push(label);
}

async function settle(page) {
  await page.waitForFunction(() =>
    [...document.querySelectorAll(".rise, .pop, .slip")].every(
      (el) => getComputedStyle(el).opacity === "1",
    ),
  );
}

/** Send a message; return the text of the reply once it has finished. */
async function say(page, text, { expectStreaming = false } = {}) {
  const before = await page.locator("[data-turn]").count();
  const box = page.getByPlaceholder(/Ask/);
  await box.fill(text);
  await box.press("Enter");

  const turn = page.locator("[data-turn]").nth(before);
  await turn.waitFor();

  let sawCaret = false;
  if (expectStreaming) {
    sawCaret = await turn
      .locator(".caret")
      .first()
      .waitFor({ timeout: 30_000 })
      .then(() => true)
      .catch(() => false);
  }

  // The turn is finished when it stops reporting itself as running.
  await page.waitForFunction(
    (i) => document.querySelectorAll("[data-turn]")[i]?.getAttribute("data-running") === "false",
    before,
    { timeout: 120_000 },
  );
  await settle(page);
  const reply = (await turn.locator("[data-reply]").innerText().catch(() => "")).trim();
  return { turn, reply, sawCaret };
}

const run = async () => {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto(BASE, { waitUntil: "networkidle" });

  console.log("\n1. greeting");
  let r = await say(page, "hello!");
  check("replies naturally", r.reply.length > 10, JSON.stringify(r.reply.slice(0, 90)));
  check("no refusal note", !(await r.turn.getByText(/No published source/).count()));
  check("no supporting cards on small talk", !(await r.turn.getByText(/Go here/).count()));

  console.log("\n2. first question");
  r = await say(page, "How do I request an official transcript?", { expectStreaming: true });
  check("answer streamed with a cursor", r.sawCaret);
  check("mentions the STS portal", /STS/i.test(r.reply));
  check("office card shown", (await r.turn.getByText(/Go here/).count()) > 0);
  check("cedi sign intact in answer", r.reply.includes("₵") || !/GH/.test(r.reply), r.reply.match(/GH.{0,4}/)?.[0]);
  await page.screenshot({ path: `${OUT}/chat-1-transcript.png` });

  console.log("\n3. follow-up with no noun in it");
  r = await say(page, "how much does it cost?");
  check("understood as the transcript fee", /30/.test(r.reply) && /₵|GH/.test(r.reply), JSON.stringify(r.reply.slice(0, 120)));
  const memory = await r.turn.getByRole("button", { name: /Checked|Writing|searched/i }).first();
  if (await memory.count()) await memory.click();
  await settle(page);
  check(
    "trace shows the rewritten question",
    (await r.turn.getByText(/Following the conversation/).count()) > 0,
  );
  await page.screenshot({ path: `${OUT}/chat-2-followup.png` });

  console.log("\n4. follow-up that changes the procedure");
  r = await say(page, "what if I graduated in 1994?");
  check("switches to the pre-1996 route", /Cash Office/i.test(r.reply) && /two weeks|2 weeks/i.test(r.reply), JSON.stringify(r.reply.slice(0, 120)));
  check("no stray lone citation line", !(await r.turn.locator("[data-reply] > div > p").filter({ hasText: /^\s*\d+\s*$/ }).count()));
  await page.screenshot({ path: `${OUT}/chat-3-1994.png` });

  console.log("\n5. off-topic");
  r = await say(page, "who won the Ghana Premier League?");
  check("declines rather than answering", !/won|champion/i.test(r.reply) || /outside|can't help|cannot help|not able/i.test(r.reply), JSON.stringify(r.reply.slice(0, 120)));

  console.log("\n6. no verified source");
  r = await say(page, "What will the 2027/2028 MBA fee be?");
  check("says it has no verified figure", /2025\/2026|not (have|hold)|don['’]t have|no verified/i.test(r.reply), JSON.stringify(r.reply.slice(0, 120)));
  check("gap is flagged", (await r.turn.getByText(/No published source/).count()) > 0);
  await page.screenshot({ path: `${OUT}/chat-4-refusal.png` });

  /* ------------------------------------------------------------ mobile ---- */
  console.log("\n7. phone");
  const phone = await browser.newPage({ ...devices["Pixel 7"] });
  phone.on("pageerror", (e) => errors.push(`[phone] ${e.message}`));
  await phone.goto(BASE, { waitUntil: "networkidle" });
  const small = await say(phone, "How do I get a student ID card?");
  const width = await phone.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
  check("no horizontal overflow", width[0] <= width[1] + 1, `${width[0]} vs ${width[1]}`);
  check("synthetic procedure labelled", (await small.turn.getByText(/Illustrative/).count()) > 0);
  await phone.screenshot({ path: `${OUT}/chat-5-phone.png` });

  await browser.close();

  console.log("\n" + "-".repeat(60));
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
