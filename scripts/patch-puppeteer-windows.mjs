import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const launcherPath = path.join(
  projectRoot,
  "node_modules",
  "@puppeteer",
  "browsers",
  "lib",
  "launch.js"
);

const unsafeDefault = "opts.detached ??= true;";
const previousWindowsDefault = "opts.detached ??= process.platform !== 'win32';";
const windowsSafeDefault =
  "opts.detached = process.platform === 'win32' ? false : (opts.detached ?? true);";

if (!fs.existsSync(launcherPath)) {
  throw new Error(`Puppeteer launcher not found: ${launcherPath}`);
}

const source = fs.readFileSync(launcherPath, "utf8");
if (!source.includes("windowsHide: true")) {
  throw new Error("Puppeteer launcher no longer sets windowsHide: true; refusing a partial patch");
}

if (source.includes(windowsSafeDefault)) {
  console.log("Puppeteer Windows launcher already uses detached: false");
} else if (source.includes(unsafeDefault) || source.includes(previousWindowsDefault)) {
  const oldDefault = source.includes(previousWindowsDefault)
    ? previousWindowsDefault
    : unsafeDefault;
  fs.writeFileSync(
    launcherPath,
    source.replace(oldDefault, windowsSafeDefault),
    "utf8"
  );
  console.log("Patched Puppeteer launcher: detached is forced off on Windows");
} else {
  throw new Error("Unsupported Puppeteer launcher shape; update the postinstall patch");
}
