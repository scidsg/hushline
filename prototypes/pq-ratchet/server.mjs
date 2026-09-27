import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const sourceRoot = resolve(root, "src");
const vendorRoot = resolve(root, "node_modules/@getmaapp/signal-wasm");
const port = Number.parseInt(process.env.PQ_PROTOTYPE_PORT || "4179", 10);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
};

function resolveInside(base, relativePath) {
  const candidate = resolve(base, relativePath);
  if (candidate !== base && !candidate.startsWith(`${base}${sep}`)) {
    return null;
  }
  return candidate;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  const strictCsp = url.searchParams.get("csp") === "conversation";
  const scriptSources = strictCsp ? "'self'" : "'self' 'wasm-unsafe-eval'";
  response.setHeader(
    "Content-Security-Policy",
    `default-src 'none'; script-src ${scriptSources}; connect-src 'self'; style-src 'self'; worker-src 'self' blob:; form-action 'none'; frame-ancestors 'none'`,
  );
  response.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  response.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
  response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Cache-Control", "no-store");

  const isVendor = url.pathname.startsWith("/vendor/");
  const base = isVendor ? vendorRoot : sourceRoot;
  const relativePath = isVendor
    ? url.pathname.slice("/vendor/".length)
    : url.pathname === "/"
      ? "index.html"
      : url.pathname.slice(1);
  const path = resolveInside(base, relativePath);
  try {
    if (!path || !(await stat(path)).isFile()) {
      throw new Error("not found");
    }
    response.statusCode = 200;
    response.setHeader(
      "Content-Type",
      mimeTypes[extname(path)] || "application/octet-stream",
    );
    createReadStream(path).pipe(response);
  } catch {
    response.statusCode = 404;
    response.setHeader("Content-Type", "text/plain; charset=utf-8");
    response.end("Not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`PQ prototype listening on http://127.0.0.1:${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
