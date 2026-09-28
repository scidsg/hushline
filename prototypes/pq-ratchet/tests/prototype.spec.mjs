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
  const environment = {
    browser_version: "Playwright engine",
    hardware: "synthetic CI runner",
    mode: "ephemeral-context",
    operating_system: "test host",
  };
  const report = await page.evaluate(
    (recordedEnvironment) =>
      window.pqPrototype.runPrototype({ environment: recordedEnvironment }),
    environment,
  );
  expect(report.synthetic_only).toBe(true);
  expect(report.operator_recorded_environment).toEqual(environment);
  expect(report.implementation.candidate).toBe("@getmaapp/signal-wasm");
  expect(report.implementation.candidate_version).toBe("0.6.6");
  expect(report.implementation.kem_is_fips_203_ml_kem).toBe(false);
  expect(report.implementation.upstream_revision).toBe(
    "b056faa6dd02961cff24064c54c089c52e1a0753",
  );
  expect(report.pqxdh.kyber_prekey_consumed).toBe(true);
  expect(report.bidirectional).toBe(true);
  expect(report.state_reload.session_continuation_passed).toBe(true);
  expect(report.state_reload.application_identity_binding_verified).toBe(true);
  expect(report.state_reload.wrapper_identity_store_export).toBe("unsupported");
  expect(report.state_reload.in_memory_export_import_passed).toBe(true);
  expect(report.state_reload.page_reload_available).toBe(true);
  expect(report.faults.dropped_message_recovered).toBe(true);
  expect(report.faults.reordered_messages_recovered).toBe(true);
  expect(report.faults.replay.rejected).toBe(true);
  expect(report.spqr.observed_epochs.length).toBeGreaterThanOrEqual(2);
  expect(report.benchmarks.timing_runs).toBeGreaterThanOrEqual(30);
  expect(report.benchmarks.warm_latency_samples_ms).toHaveLength(
    report.benchmarks.timing_runs,
  );
  expect(report.benchmarks.cold_latency_ms).toBeGreaterThan(0);
  expect(report.benchmarks.bundle_transfer_bytes).toBeGreaterThan(0);
  expect(report.benchmarks.ciphertext_amplification).toBeGreaterThan(1);
  expect(report.state_reload.serialized_state_bytes).toBeGreaterThan(0);
  expect(report.fixture_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(report.reference_peer.status).toBe("not_run");

  await page.reload();
  const resumed = await page.evaluate(() =>
    window.pqPrototype.resumePersistedPrototype(),
  );
  expect(resumed.resumed).toBe(true);

  const identityMismatch = await page.evaluate(async () => {
    const key = "hushline-pq-prototype-synthetic-state-v1";
    const saved = JSON.parse(sessionStorage.getItem(key));
    saved.alice.trusted_peer_identity = "0".repeat(64);
    sessionStorage.setItem(key, JSON.stringify(saved));
    return window.pqPrototype.resumePersistedPrototype();
  });
  expect(identityMismatch.resumed).toBe(false);
  expect(identityMismatch.reason).toBe("state-invalid");
  expect(identityMismatch.fail_closed).toBe(true);
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
        const report = await window.pqPrototype.runPrototype({
          benchmarkRuns: 0,
          epochTarget: 0,
        });
        const resume = await window.pqPrototype.resumePersistedPrototype();
        return { probe, report, resume, scenarioContinued: true };
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
    expect(result.scenarioContinued).toBe(true);
    expect(result.report.bidirectional).toBe(true);
    expect(result.report.state_reload.in_memory_export_import_passed).toBe(
      true,
    );
    expect(result.report.state_reload.page_reload_available).toBe(false);
    expect(
      result.report.state_reload.storage.fail_closed_after_page_reload,
    ).toBe(true);
    expect(result.report.state_reload.storage.name).toBe(
      mode === "quota-limited" ? "QuotaExceededError" : "SecurityError",
    );
    expect(result.resume.resumed).toBe(false);
    expect(result.resume.reason).toBe("state-unavailable");
  });
}
