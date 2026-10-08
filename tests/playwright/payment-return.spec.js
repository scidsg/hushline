const { test, expect } = require("@playwright/test");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
let server;
let origin;
let returnCookies;
let confirmationCookies;
let pending;

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    if (req.url === "/stripe") {
      res.end(
        `<a href="${origin}/single-tenant/payment-return?session_id=cs_test_owned">Return to Hush Line</a>`,
      );
    } else if (req.url.startsWith("/single-tenant/payment-return?")) {
      returnCookies.push(req.headers.cookie || "");
      res.setHeader("Content-Type", "text/html");
      res.setHeader(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; script-src-elem 'self'; connect-src 'self'",
      );
      res.setHeader("Referrer-Policy", "no-referrer");
      res.setHeader("Cache-Control", "no-store");
      res.end(
        fs
          .readFileSync(
            path.join(
              root,
              "hushline/templates/single-tenant/payment-return.html",
            ),
            "utf8",
          )
          .replace(
            "{{ script_url }}",
            "/static/js/single-tenant-payment-return.js",
          )
          .replaceAll(
            "{{ confirm_url }}",
            "/single-tenant/payment-confirm?session_id=cs_test_owned",
          )
          .replace("{{ setup_url }}", "/single-tenant"),
      );
    } else if (req.url === "/static/js/single-tenant-payment-return.js") {
      res.setHeader("Content-Type", "text/javascript");
      res.end(
        fs.readFileSync(
          path.join(root, "assets/js/single-tenant-payment-return.js"),
        ),
      );
    } else if (req.url.startsWith("/single-tenant/payment-confirm?")) {
      confirmationCookies.push(req.headers.cookie || "");
      res.setHeader("Content-Type", "application/json");
      if (!req.headers.cookie?.includes("session=owned")) {
        res.writeHead(401).end("{}");
      } else if (pending-- > 0) {
        res.writeHead(202).end('{"paid":false}');
      } else {
        res.end('{"paid":true}');
      }
    } else if (req.url === "/single-tenant") {
      res.end("<h1>Step 3: Domain setup</h1>");
    } else {
      res.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, "0.0.0.0", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
});

test.afterAll(async () => new Promise((resolve) => server.close(resolve)));

for (const delay of [0, 1]) {
  test(`Stripe return retains Strict login and automatically advances (pending=${delay})`, async ({
    page,
    context,
  }) => {
    returnCookies = [];
    confirmationCookies = [];
    pending = delay;
    await context.addCookies([
      {
        name: "session",
        value: "owned",
        url: origin,
        sameSite: "Strict",
        httpOnly: true,
        secure: true,
      },
    ]);
    // localhost and 127.0.0.1 are distinct sites. Both are trusted loopback origins.
    await page.goto(`http://localhost:${server.address().port}/stripe`);
    await page.getByRole("link", { name: "Return to Hush Line" }).click();
    await expect(
      page.getByRole("heading", { name: "Step 3: Domain setup" }),
    ).toBeVisible();
    expect(returnCookies).toEqual([""]);
    expect(confirmationCookies).toHaveLength(delay + 1);
    expect(
      confirmationCookies.every((cookie) => cookie.includes("session=owned")),
    ).toBe(true);
    expect(
      (await context.cookies(origin)).find(
        (cookie) => cookie.name === "session",
      ).sameSite,
    ).toBe("Strict");
    if (process.env.PAYMENT_RETURN_SCREENSHOT)
      await page.screenshot({ path: process.env.PAYMENT_RETURN_SCREENSHOT });
  });
}
