import { createHash, createPrivateKey, verify } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

function value(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return resolve(process.argv[index + 1]);
}
function canonical(payload) {
  const ordered = {};
  for (const key of Object.keys(payload).sort()) ordered[key] = payload[key];
  return JSON.stringify(ordered);
}

const manifest = JSON.parse(readFileSync(value("--manifest"), "utf8"));
const installerPath = value("--installer");
const privateKey = createPrivateKey(readFileSync(value("--private-key")));
if (manifest.schema !== 1 || !manifest.payload || !manifest.signature) throw new Error("Manifest is incomplete");
if (!verify("RSA-SHA256", Buffer.from(canonical(manifest.payload)), privateKey, Buffer.from(manifest.signature, "base64url"))) {
  throw new Error("Manifest signature is invalid");
}
const installer = readFileSync(installerPath);
const digest = createHash("sha256").update(installer).digest("hex").toUpperCase();
if (digest !== manifest.payload.sha256 || statSync(installerPath).size !== manifest.payload.size) {
  throw new Error("Installer does not match manifest");
}
process.stdout.write(`${manifest.payload.version}\n`);
