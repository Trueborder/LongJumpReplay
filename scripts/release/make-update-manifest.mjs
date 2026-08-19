import { createHash, createPrivateKey, sign } from "node:crypto";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

function value(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return process.argv[index + 1];
}

function canonical(payload) {
  const ordered = {};
  for (const key of Object.keys(payload).sort()) ordered[key] = payload[key];
  return JSON.stringify(ordered);
}

function releaseNotes(markdown, version) {
  const lines = markdown.split(/\r?\n/);
  const heading = new RegExp(`^##\\s+\\[?${version.replaceAll(".", "\\.")}\\]?\\b`);
  const start = lines.findIndex((line) => heading.test(line));
  if (start < 0) throw new Error(`CHANGELOG.md has no ${version} section`);
  const notes = [];
  for (const line of lines.slice(start + 1)) {
    if (/^##\s+/.test(line)) break;
    const match = /^[-*]\s+(.+)$/.exec(line.trim());
    if (match) notes.push(match[1].trim());
  }
  if (!notes.length) throw new Error(`CHANGELOG.md has no notes for ${version}`);
  return notes.slice(0, 12);
}

const version = value("--version");
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error("Version must be x.y.z");
const installer = resolve(value("--installer"));
const privateKeyPath = resolve(value("--private-key"));
const changelog = resolve(value("--changelog"));
const output = resolve(value("--output"));
const bytes = readFileSync(installer);
const payload = {
  channel: "stable",
  installer_url: `https://files.tomaspisar.cz/releases/${version}/LongJumpReplay-Setup-${version}.exe`,
  notes: releaseNotes(readFileSync(changelog, "utf8"), version),
  product: "longjumpreplay",
  published_at: new Date().toISOString(),
  sha256: createHash("sha256").update(bytes).digest("hex").toUpperCase(),
  size: statSync(installer).size,
  version,
};
const signature = sign("RSA-SHA256", Buffer.from(canonical(payload)), createPrivateKey(readFileSync(privateKeyPath))).toString("base64url");
writeFileSync(output, `${JSON.stringify({ schema: 1, payload, signature }, null, 2)}\n`, "utf8");
process.stdout.write(`${output}\n`);
