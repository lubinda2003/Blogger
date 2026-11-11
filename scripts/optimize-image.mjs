import sharp from "sharp";

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  throw new Error("Usage: node optimize-image.mjs <input> <output>");
}
await sharp(input, { failOn: "none" })
  .rotate()
  .webp({ quality: 82, effort: 5, smartSubsample: true })
  .toFile(output);
