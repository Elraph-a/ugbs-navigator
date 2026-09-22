/* Render docs/*.svg to PNG at 2x, for pasting into the report.
 *
 *     node tools/render_diagrams.mjs
 *
 * Playwright is already a dev dependency of the frontend for the interface
 * checks, so this adds nothing new to install.
 */

import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const docs = path.join(root, "docs");

// Playwright is installed under frontend/, where the interface checks use it.
const require = createRequire(path.join(root, "frontend", "package.json"));
const { chromium } = require("playwright");
const names = ["current-process", "architecture"];

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });

for (const name of names) {
  const svg = await readFile(path.join(docs, `${name}.svg`), "utf-8");
  const width = Number(svg.match(/width="(\d+)"/)[1]);
  const height = Number(svg.match(/height="(\d+)"/)[1]);

  await page.setViewportSize({ width, height });
  await page.setContent(
    `<!doctype html><meta charset="utf-8">
     <style>html,body{margin:0;background:#fff}</style>${svg}`,
    { waitUntil: "load" },
  );
  const png = await page.screenshot({ clip: { x: 0, y: 0, width, height } });
  await writeFile(path.join(docs, `${name}.png`), png);
  console.log(`${name}.png  ${width}x${height} at 2x`);
}

await browser.close();
