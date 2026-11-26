import { createRequire } from "node:module";

// Sharp is installed in tools/visuals by the workflow. Resolve it from that
// explicit location instead of relying on a root-level node_modules folder.
const require = createRequire(import.meta.url);
const sharp = require("../tools/visuals/node_modules/sharp");

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  throw new Error("Usage: node optimize-image.mjs <input> <output>");
}
await sharp(input, { failOn: "none" })
  .rotate()
  .webp({ quality: 82, effort: 5, smartSubsample: true })
  .toFile(output);
