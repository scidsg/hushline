"""Credential-bearing workflows must keep request data outside executable sources."""

import re
from pathlib import Path


def test_legacy_privileged_jobs_execute_only_trusted_base_code() -> None:
    text = Path(".github/workflows/self_service_test_deploy.yml").read_text()
    assert "  pull_request_target:" in text
    assert "  pull_request:" not in text
    assert "PYTHONPATH: ${{ github.workspace }}/trusted" in text
    assert "PYTHONPATH=request" not in text
    assert "request/scripts/" not in text
    assert "from request." not in text
    jobs = re.split(r"^  [a-z][a-z-]+:\n", text.split("jobs:\n", 1)[1], flags=re.MULTILINE)[1:]
    assert jobs
    for job in jobs:
        assert "github.ref == 'refs/heads/main'" in job
        assert "environment: self-service-test-2447" in job
        first = job.split("    steps:\n", 1)[1].split("      - name: ")[1]
        assert "ref: ${{ github.event.pull_request.base.sha }}" in first
        assert "path: trusted" in first
        for step in job.split("      - name: ")[1:]:
            if "uses: actions/checkout@" in step and (
                "pull_request.head.sha" in step or "ref: ${{ env.PR_HEAD_SHA }}" in step
            ):
                assert "path: request" in step
                assert "persist-credentials: false" in step
            assert "working-directory: request" not in step
    for name in (
        "HUSHLINE_INFRA_STAGING_PAT",
        "HUSHLINE_STAGING_DO_TOKEN",
        "HUSHLINE_STAGING_TF_TOKEN",
        "HUSHLINE_STRIPE_TEST_SECRET_KEY",
    ):
        assert "secrets." + name not in text


def test_customer_workflow_has_no_repository_credential_fallback() -> None:
    text = Path(".github/workflows/single_tenant_lifecycle.yml").read_text()
    assert "secrets.SINGLE_TENANT_CONFIG_READ_TOKEN" in text
    assert "secrets.HUSHLINE_INFRA_STAGING_PAT" not in text
    assert not re.search(r"secrets\.[A-Z_]+\s*\|\|\s*secrets\.", text)
