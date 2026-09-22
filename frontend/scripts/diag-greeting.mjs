// Where is the greeting reply, physically? Measures instead of guessing.
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto("http://localhost:3000", { waitUntil: "networkidle" });

const box = page.getByPlaceholder(/Ask/);
await box.fill("hello");
await box.press("Enter");
await page.getByText(/I answer questions about University of Ghana/).waitFor();

for (const ms of [0, 400, 1200]) {
  await page.waitForTimeout(ms);
  const m = await page.evaluate(() => {
    const scroller = [...document.querySelectorAll("div")].find(
      (d) => getComputedStyle(d).overflowY === "auto" && d.scrollHeight > 0,
    );
    const reply = [...document.querySelectorAll("p")].find((p) =>
      p.textContent?.includes("I answer questions about"),
    );
    const bubble = [...document.querySelectorAll("p")].find(
      (p) => p.textContent?.trim() === "hello",
    );
    const r = reply?.getBoundingClientRect();
    const b = bubble?.getBoundingClientRect();
    const chain = [];
    for (let el = reply; el && el !== document.body; el = el.parentElement) {
      const cs = getComputedStyle(el);
      if (cs.opacity !== "1" || cs.transform !== "none" || cs.visibility !== "visible")
        chain.push(`${el.tagName}.${(el.className || "").toString().slice(0, 30)} op=${cs.opacity} tf=${cs.transform}`);
    }
    return {
      scrollTop: scroller?.scrollTop,
      scrollHeight: scroller?.scrollHeight,
      clientHeight: scroller?.clientHeight,
      replyTop: r && Math.round(r.top),
      replyHeight: r && Math.round(r.height),
      bubbleTop: b && Math.round(b.top),
      hiddenAncestors: chain,
    };
  });
  console.log(`+${ms}ms`, JSON.stringify(m, null, 1));
}

await browser.close();
