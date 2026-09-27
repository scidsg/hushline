import { expect, test } from "@playwright/test";

test("current conversation CSP does not silently broaden for WASM", async ({
  page,
}) => {
  const response = await page.goto("/?csp=conversation");
  const csp = response.headers()["content-security-policy"];
  const outcome = await page.evaluate(async () => {
    try {
      await window.pqPrototype.runPrototype({
        benchmarkRuns: 0,
        epochTarget: 0,
      });
      return { ran: true };
    } catch (error) {
      return { ran: false, name: error.name };
    }
  });
  expect(outcome.ran).toBe(false);
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toContain("wasm-unsafe-eval");
});

test("offline PQXDH and two observed SPQR epochs survive traffic faults and reload", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  const report = await page.evaluate(() => window.pqPrototype.runPrototype());
  expect(report.synthetic_only).toBe(true);
  expect(report.pqxdh.kyber_prekey_consumed).toBe(true);
  expect(report.bidirectional).toBe(true);
  expect(report.state_reload.session_continuation_passed).toBe(true);
  expect(report.state_reload.identity_trust_persistence).toBe(
    "unsupported-by-wrapper",
  );
  expect(report.state_reload.acceptance_passed).toBe(false);
  expect(report.faults.dropped_message_recovered).toBe(true);
  expect(report.faults.reordered_messages_recovered).toBe(true);
  expect(report.faults.replay.rejected).toBe(true);
  expect(report.spqr.observed_epochs.length).toBeGreaterThanOrEqual(2);
  expect(report.benchmarks.timing_runs).toBeGreaterThanOrEqual(30);
  expect(report.benchmarks.cold_latency_ms).toBeGreaterThan(0);
  expect(report.benchmarks.bundle_transfer_bytes).toBeGreaterThan(0);
  expect(report.benchmarks.ciphertext_amplification).toBeGreaterThan(1);
  expect(report.state_reload.session_storage_bytes).toBeGreaterThan(0);
  expect(report.reference_peer.status).toBe("not_run");

  await page.reload();
  const resumed = await page.evaluate(() =>
    window.pqPrototype.resumePersistedPrototype(),
  );
  expect(resumed.resumed).toBe(true);
  await testInfo.attach("pq-ratchet-non-secret-report", {
    body: JSON.stringify({ ...report, page_reload: resumed }, null, 2),
    contentType: "application/json",
  });
});

for (const mode of ["unavailable", "quota-limited"]) {
  test(`storage ${mode} fails closed`, async ({ page }) => {
    await page.addInitScript((storageMode) => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function setItem(key, value) {
        if (key.includes("hushline-pq-prototype")) {
          throw new DOMException(
            storageMode === "quota-limited"
              ? "Synthetic quota"
              : "Synthetic denial",
            storageMode === "quota-limited"
              ? "QuotaExceededError"
              : "SecurityError",
          );
        }
        return original.call(this, key, value);
      };
    }, mode);
    await page.goto("/");
    const result = await page.evaluate(async () => {
      const probe = window.pqPrototype.probeStorage();
      try {
        await window.pqPrototype.runPrototype({
          benchmarkRuns: 0,
          epochTarget: 0,
        });
        return { probe, scenarioContinued: true };
      } catch (error) {
        return {
          probe,
          scenarioContinued: false,
          scenarioError: { name: error.name },
        };
      }
    });
    expect(result.probe.available).toBe(false);
    expect(result.probe.fail_closed).toBe(true);
    expect(result.scenarioContinued).toBe(false);
    expect(result.scenarioError.name).toBe(
      mode === "quota-limited" ? "QuotaExceededError" : "SecurityError",
    );
  });
}
