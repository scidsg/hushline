"""Independent health rows retain passed checks without automatic navigation."""

import json
import os
import subprocess

import pytest


@pytest.mark.parametrize("failed", [False, True])
def test_real_progress_respects_independent_checks(failed: bool) -> None:
    result = {
        "state": "failed" if failed else "provisioning",
        "ingress": "already-created-provider-host",
        "https_ok": False,
        "checks": {"infrastructure": True, "configuration": False, "tls": False, "health": False},
        "message": "Checking health",
        "ready": False,
    }
    script = r"""
      const fs = require('node:fs');
      const vm = require('node:vm');
      const result = JSON.parse(process.env.PROGRESS_TEST_RESULT);
      const rows = Array.from({length: 4}, () => ({dataset: {},
        querySelector: () => ({textContent: '', prepend() {}})}));
      const checks = {dataset: {real: 'true'}, querySelectorAll: () => rows};
      const complete = {hidden: false};
      const document = {
        addEventListener: (_, callback) => callback(),
        getElementById: id => ({'deployment-checks': checks,
          'deployment-status': {}, 'deployment-complete': complete})[id] || null,
        createElementNS: () => ({setAttribute() {}, append() {}})
      };
      vm.runInNewContext(fs.readFileSync('assets/js/single-tenant-progress.js', 'utf8'), {
        document, Date, fetch: async () => ({ok: true, json: async () => result}),
        setTimeout() {},
        window: {location: {assign() {throw new Error('Automatic advance');}}}
      });
      setImmediate(() => process.stdout.write(JSON.stringify({
        states: rows.map(row => row.dataset.state), hidden: complete.hidden
      })));
    """
    observed = subprocess.run(
        ["node", "-e", script],  # noqa: S603,S607 — fixed local JavaScript test harness
        env={**os.environ, "PROGRESS_TEST_RESULT": json.dumps(result)},
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    data = json.loads(observed.stdout)
    assert data["states"] == ["passed", *(["failed" if failed else "running"] * 3)]
    assert data["hidden"] is True
