/* Fetch one page the way a browser would, and print its HTML.
 *
 *     node tools/render_page.mjs <url>
 *
 * Some University pages build their content with JavaScript, so a plain HTTP
 * request returns an empty shell. tools/collect_sources.py falls back to this
 * when an extraction looks like a shell or a navigation menu.
 *
 * Playwright is already installed under frontend/ for the interface checks.
 */

import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(root, "frontend", "package.json"));
const { chromium } = require("playwright");

const url = process.argv[2];
if (!url) {
  console.error("usage: node tools/render_page.mjs <url>");
  process.exit(2);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    userAgent:
      "UGBS-Service-Navigator/0.1 (University of Ghana OMIS 404 student project; " +
      "indexing published administrative procedures)",
  });
  await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 });
  // Content often arrives just after the network settles.
  await page.waitForTimeout(1500);
  process.stdout.write(await page.content());
} finally {
  await browser.close();
}
