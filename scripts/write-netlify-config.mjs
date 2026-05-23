import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputPath = resolve(root, "frontend/static/config.js");
const apiBaseUrl = process.env.SPECLINT_API_BASE_URL || "";

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(
  outputPath,
  `window.SPECLINT_CONFIG = ${JSON.stringify({ apiBaseUrl }, null, 2)};\n`,
);
