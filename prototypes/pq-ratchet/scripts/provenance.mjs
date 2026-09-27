import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const packageRoot = resolve(root, "node_modules/@getmaapp/signal-wasm");
const expected = {
  sourceRevision: "0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd",
  files: {
    LICENSE: "2b87ae924bd39116783dbb5d33770a9fcd4d62a5578204c6304f572bcdc5f091",
    "README.md":
      "6c1b3f948eec9e7d8527dd5d5ad6fb5b2405e059a51ce292baadd7cdb0d2fe26",
    "package.json":
      "677b54900bf2c8fc422e7771efd90d1a5c10b251402c8bcae27d5fd445cddded",
    "signal_wasm.d.ts":
      "32441be517be4cf6b5bd12506e756d07dabb84859941cffb56657ff4c9dad7f2",
    "signal_wasm.js":
      "c72af7ae13a17fca0b0c2a2b8acb948c9eb9c71a17f9c4194c53bdf2ab883410",
    "signal_wasm_bg.wasm":
      "71b456b8a1bfc93111be86fdff9726ed397de55f223ee9136dab619a6620d6c1",
  },
};
let lock;
try {
  lock = JSON.parse(await readFile(resolve(root, "package-lock.json"), "utf8"));
} catch {
  throw new Error(
    "package-lock.json is missing; generate it from the trusted registry and review its integrity pin",
  );
}
const entry = lock.packages?.["node_modules/@getmaapp/signal-wasm"];
if (
  !entry ||
  entry.version !== "0.6.6" ||
  !entry.integrity ||
  !entry.resolved
) {
  throw new Error(
    "signal-wasm 0.6.6 must have a resolved URL and integrity pin",
  );
}
if (!entry.integrity.startsWith("sha512-")) {
  throw new Error("signal-wasm must use an npm SHA-512 integrity pin");
}
const packageJsonBytes = await readFile(resolve(packageRoot, "package.json"));
const packageJson = JSON.parse(packageJsonBytes.toString("utf8"));
if (packageJson.version !== entry.version) {
  throw new Error(
    "installed signal-wasm version does not match package-lock.json",
  );
}
if (packageJson.license !== "AGPL-3.0-only") {
  throw new Error("installed signal-wasm license declaration is unexpected");
}
const installedFiles = (await readdir(packageRoot)).sort();
const expectedFiles = Object.keys(expected.files).sort();
if (JSON.stringify(installedFiles) !== JSON.stringify(expectedFiles)) {
  throw new Error("installed signal-wasm file inventory is unexpected");
}
const fileSha256 = {};
for (const [file, expectedSha256] of Object.entries(expected.files)) {
  const bytes = await readFile(resolve(packageRoot, file));
  const actualSha256 = createHash("sha256").update(bytes).digest("hex");
  if (actualSha256 !== expectedSha256) {
    throw new Error(
      `installed signal-wasm ${file} does not match reviewed hash`,
    );
  }
  fileSha256[file] = actualSha256;
}
process.stdout.write(
  `${JSON.stringify(
    {
      schema_version: 1,
      package: "@getmaapp/signal-wasm",
      version: entry.version,
      resolved: entry.resolved,
      npm_integrity: entry.integrity,
      declared_license: packageJson.license ?? null,
      declared_repository: packageJson.repository ?? null,
      published_source_revision: expected.sourceRevision,
      file_sha256: fileSha256,
    },
    null,
    2,
  )}\n`,
);
