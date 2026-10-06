// Real test status comes from the server; the default UI demo keeps simulated progress.
document.addEventListener("DOMContentLoaded", () => {
  function deploymentMessage(result) {
    const started = Date.parse(result.deployment_started_at);
    if (!Number.isFinite(started)) return result.message;
    const elapsed = Math.max(0, Math.floor((Date.now() - started) / 1000));
    return `${result.message} · This attempt: ${Math.floor(elapsed / 60)}m ${elapsed % 60}s elapsed.`;
  }
  function setState(row, state) {
    row.dataset.state = state;
    const status = row.querySelector(".check-state");
    status.textContent = {
      pending: "○ Pending",
      running: "◌ Checking…",
      passed: "Passed",
      failed: "! Failed",
    }[state];
    if (state === "passed") {
      const namespace = "http://www.w3.org/2000/svg";
      const icon = document.createElementNS(namespace, "svg");
      icon.setAttribute("viewBox", "0 0 20 20");
      icon.setAttribute("class", "passed-icon");
      icon.setAttribute("aria-hidden", "true");
      icon.setAttribute("focusable", "false");
      const path = document.createElementNS(namespace, "path");
      path.setAttribute("fill", "currentColor");
      path.setAttribute("fill-rule", "evenodd");
      path.setAttribute(
        "d",
        "M10 0a10 10 0 1 0 0 20a10 10 0 1 0 0-20Z M3.5 10.5l4.5 4.5 8.5-8.5-1.5-1.5-7 7-3-3Z",
      );
      icon.append(path);
      status.prepend(icon);
    }
  }
  function showRetry() {
    // Reconcile the same saved request; never expose a replacement deployment.
  }
  const fixtureProgress = document.getElementById("fixture-progress");
  if (fixtureProgress) {
    async function pollFixture() {
      try {
        const response = await fetch("/single-tenant/status");
        if (!response.ok) throw new Error("Status unavailable");
        const result = await response.json();
        fixtureProgress.textContent = deploymentMessage(result);
        document.getElementById("fixture-endpoint").textContent =
          result.ingress || "Hostname available after provisioning.";
        document.getElementById("fixture-continue").hidden = !result.ready;
        if (result.ready || result.state === "failed") return;
      } catch (error) {
        fixtureProgress.textContent =
          "Status temporarily unavailable. Retrying read-only checks…";
      }
      setTimeout(pollFixture, 5000);
    }
    pollFixture();
  }
  const dnsForm = document.getElementById("dns-verification");
  if (dnsForm) {
    const checks = document.getElementById("dns-checks");
    const rows = [...checks.querySelectorAll(".setup-check")];
    if (checks.dataset.verified === "true")
      rows.forEach((row) => setState(row, "passed"));
    if (checks.dataset.failed === "true")
      rows.forEach((row) => setState(row, "failed"));
    dnsForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const button = dnsForm.querySelector("button");
      button.disabled = true;
      const existingContinue = document.getElementById("dns-continue");
      if (existingContinue) existingContinue.hidden = true;
      let notice = document.getElementById("dns-live-status");
      if (!notice) {
        notice = document.createElement("p");
        notice.id = "dns-live-status";
        notice.className = "meta";
        notice.setAttribute("role", "status");
        dnsForm.after(notice);
      }
      notice.textContent = "Checking DNS records…";
      async function saveChecks() {
        try {
          const response = await fetch(dnsForm.action, {
            method: "POST",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
            body: new FormData(dnsForm),
          });
          const result = await response.json();
          if (!response.ok || !result.dns_verified)
            throw new Error("DNS checks could not be confirmed. Try again.");
          rows.forEach((row) => setState(row, "passed"));
          const continueForm = dnsForm.cloneNode(true);
          continueForm.id = "dns-continue";
          continueForm.querySelector('[name="dns_action"]').value = "continue";
          const continueButton = continueForm.querySelector("button");
          continueButton.disabled = false;
          continueButton.textContent = "Continue to deployment";
          if (existingContinue) existingContinue.replaceWith(continueForm);
          else notice.after(continueForm);
          checks.dataset.verified = "true";
          checks.dataset.failed = "false";
          button.textContent = "Recheck DNS records";
          notice.textContent =
            "DNS checks passed. Continue when you're ready to deploy.";
        } catch (error) {
          rows.forEach((row) => setState(row, "failed"));
          notice.textContent = "DNS checks could not be confirmed. Try again.";
        } finally {
          button.disabled = false;
        }
      }
      let index = 0;
      function next() {
        if (index === rows.length) {
          saveChecks();
          return;
        }
        const row = rows[index++];
        setState(row, "running");
        setTimeout(() => {
          setState(row, "passed");
          next();
        }, 700);
      }
      if (checks.dataset.real === "true") {
        rows.forEach((row) => setState(row, "running"));
        saveChecks();
      } else next();
    });
  }
  const realDns = document.getElementById("dns-target");
  if (realDns) {
    async function pollDns() {
      try {
        const response = await fetch("/single-tenant/status");
        if (!response.ok) throw new Error("Status unavailable");
        const result = await response.json();
        realDns.textContent = result.ingress || "Waiting for infrastructure…";
        document.getElementById("infrastructure-status").textContent =
          deploymentMessage(result);
        const button = dnsForm.querySelector("button");
        button.disabled = !result.ingress || result.state === "failed";
        if (result.state === "failed") {
          showRetry(dnsForm);
        } else {
          document.getElementById("deployment-retry")?.remove();
        }
      } catch (error) {
        document.getElementById("infrastructure-status").textContent =
          "Deployment status temporarily unavailable. Retrying…";
      }
      setTimeout(pollDns, 5000);
    }
    dnsForm.querySelector("button").disabled = true;
    pollDns();
  }
  const checks = document.getElementById("deployment-checks");
  if (!checks) return;
  const rows = [...checks.querySelectorAll(".setup-check")];
  const status = document.getElementById("deployment-status");
  if (checks.dataset.real === "true") {
    async function pollDeployment() {
      try {
        const response = await fetch("/single-tenant/status");
        if (!response.ok) throw new Error("Status unavailable");
        const result = await response.json();
        rows.forEach((row, index) => {
          const passed = index < 2 ? !!result.ingress : !!result.https_ok;
          setState(
            row,
            passed
              ? "passed"
              : result.state === "failed"
                ? "failed"
                : "running",
          );
        });
        status.textContent = deploymentMessage(result);
        document.getElementById("deployment-complete").hidden = !result.ready;
        if (result.state === "failed") {
          showRetry(document.getElementById("deployment-complete"));
        } else {
          document.getElementById("deployment-retry")?.remove();
        }
        if (result.ready) return;
      } catch (error) {
        status.textContent =
          "Deployment status temporarily unavailable. Retrying…";
      }
      setTimeout(pollDeployment, 5000);
    }
    pollDeployment();
    return;
  }
  if (checks.dataset.failed === "true") {
    rows.forEach((row, index) =>
      setState(row, index === rows.length - 1 ? "failed" : "passed"),
    );
    status.textContent =
      "Application health check failed. Retry deployment; your payment is saved.";
    return;
  }
  let index = 0;
  let timer;
  const failureControls = document.querySelector("details");
  function advance() {
    if (failureControls?.open) return;
    if (index > 0) setState(rows[index - 1], "passed");
    if (index === rows.length) {
      status.textContent =
        "All deployment checks passed. Continue when you’re ready.";
      document.getElementById("deployment-complete").hidden = false;
      return;
    }
    setState(rows[index], "running");
    status.textContent =
      "Checking " +
      rows[index].querySelector("strong").textContent.toLowerCase() +
      "…";
    index += 1;
    timer = setTimeout(advance, 900);
  }
  failureControls?.addEventListener("toggle", () => {
    clearTimeout(timer);
    if (failureControls.open)
      status.textContent = "Demo progress paused while testing a failure.";
    else advance();
  });
  advance();
});
