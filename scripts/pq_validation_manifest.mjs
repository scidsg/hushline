#!/usr/bin/env node

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { chromium, firefox, webkit } from "playwright";

const outputPath = process.argv[2] || "test-results/pq-delivery/manifest.json";
const sha256 = (filePath) =>
  createHash("sha256").update(readFileSync(filePath)).digest("hex");
const revision =
  process.env.GITHUB_SHA ||
  execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const serverUrl = process.env.GITHUB_SERVER_URL;
const repository = process.env.GITHUB_REPOSITORY;
const runId = process.env.GITHUB_RUN_ID;
const runUrl =
  serverUrl && repository && runId
    ? `${serverUrl}/${repository}/actions/runs/${runId}`
    : null;
const playwrightPackage = JSON.parse(
  readFileSync("node_modules/playwright/package.json", "utf8"),
);
const dependencyLock = JSON.parse(readFileSync("package-lock.json", "utf8"));
const protocolDependency =
  dependencyLock.packages["node_modules/@getmaapp/signal-wasm"];

const browserVersions = {};
for (const [name, browserType] of Object.entries({
  chromium,
  firefox,
  webkit,
})) {
  const browser = await browserType.launch({ headless: true });
  browserVersions[name] = browser.version();
  await browser.close();
}

const hashedFiles = [
  "package-lock.json",
  "assets/js/chat-key-lifecycle.js",
  "assets/js/pq-browser-state.js",
  "assets/js/pq-protocol-worker.js",
  "assets/js/pq-protocol.js",
  "hushline/static/js/chat-key-lifecycle.js",
  "hushline/static/js/pq-browser-state.js",
  "hushline/static/js/pq-protocol-worker.js",
  "hushline/static/js/pq-protocol.js",
];
const hashes = Object.fromEntries(
  hashedFiles.map((filePath) => [filePath, sha256(filePath)]),
);

const manifest = {
  schema_version: 1,
  implementation_commit: revision,
  ci_run: runUrl,
  generated_at_utc: new Date().toISOString(),
  synthetic_data_only: true,
  command: "npm run playwright:pq-delivery",
  protocol: {
    name: "HL-PQCHAT-1",
    transport_suite: "SIGNAL-PQXDH3-KYBER1024-SPQR1",
    dependency: `@getmaapp/signal-wasm@${protocolDependency.version}`,
    resolved: protocolDependency.resolved,
    npm_integrity: protocolDependency.integrity,
    wrapper_source_revision: "0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd",
    libsignal_source_revision: "b056faa6dd02961cff24064c54c089c52e1a0753",
    serialization_version: 1,
    wire_version: 1,
  },
  feature_configuration: {
    PQ_CHAT_AUTO_MIGRATION_ENABLED:
      process.env.PQ_CHAT_AUTO_MIGRATION_ENABLED || null,
    PQ_CHAT_MIGRATION_ROLLOUT_PERCENT:
      process.env.PQ_CHAT_MIGRATION_ROLLOUT_PERCENT || null,
  },
  runtime: {
    node: process.version,
    playwright: playwrightPackage.version,
    browsers: browserVersions,
  },
  runner: {
    platform: os.platform(),
    release: os.release(),
    architecture: os.arch(),
    cpu_model: os.cpus()[0]?.model || null,
    logical_cpus: os.cpus().length,
    memory_bytes: os.totalmem(),
  },
  sha256: hashes,
  limitations: [
    "Playwright WebKit is not branded Safari or an iOS device result.",
    "Firefox automation is not a Tor Browser result.",
    "Human review and external-browser results remain separate release gates.",
  ],
};

mkdirSync(path.dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, {
  mode: 0o600,
});
