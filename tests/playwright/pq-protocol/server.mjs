import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

const root = resolve("hushline/static/js");
const port = Number.parseInt(process.env.PQ_PROTOCOL_TEST_PORT || "4180", 10);
const mimeTypes = {
  ".js": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
};

function insideRoot(relativePath) {
  const path = resolve(root, relativePath);
  return path === root || path.startsWith(`${root}${sep}`) ? path : null;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  response.setHeader("X-Content-Type-Options", "nosniff");

  if (url.pathname === "/") {
    response.statusCode = 200;
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.setHeader(
      "Content-Security-Policy",
      "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'",
    );
    response.end(`<!doctype html>
      <html lang="en"><head><meta charset="utf-8"><title>PQ protocol test</title>
      <script defer src="/pq-protocol.js" data-worker-url="/pq-protocol-worker.js"></script>
      <script defer src="/pq-browser-state.js"></script></head><body></body></html>`);
    return;
  }

  const relativePath = url.pathname.slice(1);
  const path = insideRoot(relativePath);
  try {
    if (!path || !(await stat(path)).isFile()) throw new Error("not found");
    response.statusCode = 200;
    response.setHeader(
      "Content-Type",
      mimeTypes[extname(path)] || "application/octet-stream",
    );
    if (relativePath === "pq-protocol-worker.js") {
      response.setHeader(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'",
      );
    }
    createReadStream(path).pipe(response);
  } catch {
    response.statusCode = 404;
    response.setHeader("Content-Type", "text/plain; charset=utf-8");
    response.end("Not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`PQ protocol test server listening on ${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
