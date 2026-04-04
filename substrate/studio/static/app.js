const state = {
  jobs: [],
  runs: [],
  settings: null,
  connection: null,
  cloudTargets: [],
  deviceAuth: null,
  cloudReadiness: null,
  notificationReadiness: null,
  preflight: null,
  systemRuntime: null,
  editingJobId: null,
};
let connectCooldownTimer = null;
let connectCooldownSeconds = 0;
let deviceCodeExpiryTimer = null;
let cloudReadinessRefreshTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || text || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function formatDate(value) {
  if (!value) return "n/a";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function statusBadgeClass(status) {
  if (status === "completed") return "success";
  if (status === "ok") return "success";
  if (status === "degraded") return "warning";
  if (status === "running") return "warning";
  if (status === "failed" || status === "timed_out") return "danger";
  return "info";
}

function notificationBadgeClass(status) {
  if (status === "sent") return "success";
  if (status === "failed") return "danger";
  return "info";
}

function categoryToBadge(category, ready) {
  if (ready) return "success";
  if (category === "provider_transient" || category === "rate_limited") return "warning";
  if (category === "auth_missing" || category === "auth_invalid" || category === "env_missing") return "danger";
  return "info";
}

function parseReadinessFromError(error) {
  return error?.payload?.detail?.readiness || null;
}

function openFallbackPanel() {
  const advanced = document.querySelector(".advanced-panel");
  if (advanced && !advanced.open) {
    advanced.open = true;
  }
  const apiKeyInput = document.getElementById("settingsApiKey");
  if (apiKeyInput) {
    apiKeyInput.focus();
  }
}

function wizardStepState(index, readiness) {
  const connected = state.settings?.last_connection_status === "ok";
  const hasEnv = Boolean(currentDefaultCloudEnvId());
  if (index === 1) {
    if (connected) return "done";
    return state.settings?.last_connection_status ? "active" : "todo";
  }
  if (index === 2) {
    if (!connected) return "todo";
    return hasEnv ? "done" : "active";
  }
  if (index === 3) {
    if (!connected || !hasEnv) return "todo";
    if (!readiness) return "active";
    return readiness.ready ? "done" : "active";
  }
  if (index === 4) {
    return readiness?.ready ? "done" : "todo";
  }
  return "todo";
}

function wizardProgressLabel(readiness) {
  const connected = state.settings?.last_connection_status === "ok";
  const hasEnv = Boolean(currentDefaultCloudEnvId());
  if (readiness?.ready) return "Step 4 of 4";
  if (readiness) return "Step 3 of 4";
  if (connected && hasEnv) return "Step 3 of 4";
  if (connected) return "Step 2 of 4";
  return "Step 1 of 4";
}

function updateJobFormGate() {
  const saveBtn = document.getElementById("saveBtn");
  if (!saveBtn) return;
  const isCloud = document.getElementById("mode").value === "cloud_exec";
  const enabled = document.getElementById("enabled").checked;
  const blocked = isCloud && enabled && !state.cloudReadiness?.ready;
  saveBtn.disabled = blocked;
  saveBtn.title = blocked ? "Cloud readiness must be green before saving an enabled cloud job." : "";
}

function scheduleCloudReadinessRefresh() {
  if (cloudReadinessRefreshTimer) {
    clearTimeout(cloudReadinessRefreshTimer);
  }
  cloudReadinessRefreshTimer = setTimeout(() => {
    refreshCloudReadiness().catch(() => {});
  }, 300);
}

function syncCloudEnvFromDefault() {
  if (state.editingJobId) return;
  renderJobCloudTargetControls();
}

function currentDefaultCloudEnvId() {
  const selected = document.getElementById("settingsDefaultCloudTargetSelect")?.value?.trim();
  const manual = document.getElementById("settingsDefaultCloudEnvId")?.value?.trim();
  return selected || manual || state.settings?.default_cloud_env_id || null;
}

function currentJobCloudEnvId() {
  if (document.getElementById("mode").value !== "cloud_exec") return null;
  if (document.getElementById("jobUseDefaultCloudTarget").checked) return currentDefaultCloudEnvId();
  const selected = document.getElementById("jobCloudTargetSelect")?.value?.trim();
  const manual = document.getElementById("jobCloudTargetManual")?.value?.trim();
  return selected || manual || null;
}

function renderCloudTargetOptions(selectId, includeBlankLabel) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const current = select.value;
  const options = [];
  if (includeBlankLabel) {
    options.push(`<option value="">${includeBlankLabel}</option>`);
  }
  for (const target of state.cloudTargets) {
    const suffix = target.repo && target.repo !== target.id ? ` (${target.repo})` : "";
    options.push(`<option value="${target.id}">${target.label}${suffix}</option>`);
  }
  select.innerHTML = options.join("");
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function renderCloudTargets() {
  renderCloudTargetOptions("settingsDefaultCloudTargetSelect", "Select a cloud target");
  renderCloudTargetOptions("jobCloudTargetSelect", "Select a job override target");
  const status = document.getElementById("cloudTargetsStatus");
  status.textContent = state.cloudTargets.length
    ? `${state.cloudTargets.length} cloud target${state.cloudTargets.length === 1 ? "" : "s"} available.`
    : "No cloud targets loaded. Use Refresh Targets or enter one manually.";
}

function renderJobCloudTargetControls() {
  const useDefault = document.getElementById("jobUseDefaultCloudTarget").checked;
  const select = document.getElementById("jobCloudTargetSelect");
  const manualPanel = document.getElementById("jobCloudTargetManualPanel");
  const hint = document.getElementById("jobCloudTargetHint");
  select.classList.toggle("hidden", useDefault);
  manualPanel.classList.toggle("hidden", useDefault);
  hint.textContent = useDefault
    ? `This job will inherit the global cloud target: ${currentDefaultCloudEnvId() || "none selected"}.`
    : "This job uses an explicit cloud target override.";
}

function renderJobs() {
  const list = document.getElementById("jobList");
  const search = (document.getElementById("jobSearch").value || "").toLowerCase().trim();
  list.innerHTML = "";
  const template = document.getElementById("jobItemTemplate");
  for (const job of state.jobs.filter((j) => j.name.toLowerCase().includes(search))) {
    const node = template.content.cloneNode(true);
    node.querySelector(".job-name").textContent = job.name;
    node.querySelector(".job-sub").textContent = `${job.mode} • ${job.schedule_type === "cron" ? job.cron_expr : `${job.interval_minutes}m`} • last: ${job.last_status || "never"}`;
    const statusBadge = node.querySelector(".status-badge");
    statusBadge.classList.add(statusBadgeClass(job.last_status));
    statusBadge.textContent = job.enabled ? "enabled" : "disabled";

    node.querySelector(".run-now-btn").addEventListener("click", () => runNow(job.id));
    node.querySelector(".edit-btn").addEventListener("click", () => loadJobToForm(job));
    node.querySelector(".toggle-btn").textContent = job.enabled ? "Disable" : "Enable";
    node.querySelector(".toggle-btn").addEventListener("click", () => toggleJob(job.id, !job.enabled));
    node.querySelector(".delete-btn").addEventListener("click", () => deleteJob(job.id));
    list.appendChild(node);
  }
}

function renderRuns() {
  const wrap = document.getElementById("runTableWrap");
  if (!state.runs.length) {
    wrap.innerHTML = "<p>No runs yet.</p>";
    return;
  }
  const rows = state.runs
    .map((run) => `<tr>
      <td>${run.id}</td>
      <td>${run.job_id}</td>
      <td><span class="badge ${statusBadgeClass(run.status)}">${run.status}</span></td>
      <td title="${(run.notification_error || "").replaceAll('"', "&quot;")}"><span class="badge ${notificationBadgeClass(run.notification_status)}">${run.notification_status || "skipped"}</span></td>
      <td>${run.return_code ?? "n/a"}</td>
      <td>${formatDate(run.started_at)}</td>
      <td>${formatDate(run.finished_at)}</td>
      <td title="${(run.message || "").replaceAll('"', "&quot;")}">${(run.message || "").slice(0, 120) || "n/a"}</td>
    </tr>`)
    .join("");
  wrap.innerHTML = `<table><thead><tr><th>Run</th><th>Job</th><th>Status</th><th>Email</th><th>Code</th><th>Started</th><th>Finished</th><th>Message</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function setText(id, message) {
  document.getElementById(id).textContent = message;
}

function setConnectionHint(message) {
  setText("connectionHint", message || "");
}

function setConnectionError(message) {
  const node = document.getElementById("connectionError");
  if (!message) {
    node.textContent = "";
    node.classList.add("hidden");
    return;
  }
  node.textContent = message;
  node.classList.remove("hidden");
}

function clearConnectionError() {
  setConnectionError("");
}

function stripAnsi(value) {
  return String(value || "").replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "");
}

function parseExpiryFromText(rawText) {
  const text = stripAnsi(rawText).toLowerCase();
  const minuteMatch = text.match(/expires in\s+(\d+)\s+minutes?/);
  if (minuteMatch) return Number(minuteMatch[1]) * 60;
  const secondMatch = text.match(/expires in\s+(\d+)\s+seconds?/);
  if (secondMatch) return Number(secondMatch[1]);
  return null;
}

function friendlyConnectionError(rawMessage) {
  const text = stripAnsi(rawMessage || "");
  if (!text) return "";
  if (text.toLowerCase().includes("follow these steps to sign in")) return "";
  return text.slice(0, 220);
}

function formatCountdown(seconds) {
  const clamped = Math.max(0, Number(seconds || 0));
  const mins = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function renderDeviceAuthCard() {
  const card = document.getElementById("deviceAuthCard");
  if (!state.deviceAuth?.verificationUrl || !state.deviceAuth?.userCode) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  setText("verificationUrlText", state.deviceAuth.verificationUrl);
  setText("deviceCodeText", state.deviceAuth.userCode);
  const expiryNode = document.getElementById("deviceCodeExpiry");

  if (deviceCodeExpiryTimer) {
    clearInterval(deviceCodeExpiryTimer);
    deviceCodeExpiryTimer = null;
  }

  const expiresAt = state.deviceAuth.expiresAt;
  if (!expiresAt) {
    expiryNode.textContent = "";
    return;
  }
  const tick = () => {
    const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
    if (remaining <= 0) {
      expiryNode.textContent = "Code expired. Click Connect Account to generate a new code.";
      if (deviceCodeExpiryTimer) {
        clearInterval(deviceCodeExpiryTimer);
        deviceCodeExpiryTimer = null;
      }
      return;
    }
    expiryNode.textContent = `Code expires in ${formatCountdown(remaining)}`;
  };
  tick();
  deviceCodeExpiryTimer = setInterval(tick, 1000);
}

function clearForm() {
  state.editingJobId = null;
  document.getElementById("jobForm").reset();
  document.getElementById("jobId").value = "";
  document.getElementById("enabled").checked = true;
  document.getElementById("timeoutSeconds").value = "1800";
  document.getElementById("workingDirectory").value = ".";
  document.getElementById("attempts").value = "1";
  document.getElementById("codexArgs").value = "";
  document.getElementById("jobEnvJson").value = "";
  document.getElementById("notifyEmailEnabled").checked = false;
  document.getElementById("notifyEmailTo").value = "";
  document.getElementById("notifyEmailToGroup").classList.add("hidden");
  document.getElementById("formTitle").textContent = "Create Job";
  document.getElementById("saveBtn").textContent = "Create Job";
  toggleModeFields();
  toggleScheduleFields();
  updateJobFormGate();
  scheduleCloudReadinessRefresh();
}

function loadJobToForm(job) {
  state.editingJobId = job.id;
  document.getElementById("jobId").value = String(job.id);
  document.getElementById("name").value = job.name;
  document.getElementById("mode").value = job.mode;
  document.getElementById("scheduleType").value = job.schedule_type;
  document.getElementById("cronExpr").value = job.cron_expr || "";
  document.getElementById("intervalMinutes").value = job.interval_minutes || "";
  document.getElementById("prompt").value = job.prompt;
  document.getElementById("sandbox").value = job.sandbox || "read-only";
  document.getElementById("workingDirectory").value = job.working_directory || ".";
  document.getElementById("timeoutSeconds").value = job.timeout_seconds || 1800;
  document.getElementById("jobUseDefaultCloudTarget").checked = !job.cloud_env_id;
  if (job.cloud_env_id) {
    document.getElementById("jobCloudTargetSelect").value = job.cloud_env_id;
    document.getElementById("jobCloudTargetManual").value = job.cloud_env_id;
  } else {
    document.getElementById("jobCloudTargetSelect").value = "";
    document.getElementById("jobCloudTargetManual").value = "";
  }
  document.getElementById("attempts").value = job.attempts || 1;
  document.getElementById("enabled").checked = !!job.enabled;
  document.getElementById("codexArgs").value = job.codex_args || "";
  document.getElementById("jobEnvJson").value = job.env_json || "";
  document.getElementById("notifyEmailEnabled").checked = !!job.notify_email_enabled;
  document.getElementById("notifyEmailTo").value = job.notify_email_to || "";
  document.getElementById("notifyEmailToGroup").classList.toggle("hidden", !job.notify_email_enabled);
  document.getElementById("formTitle").textContent = "Edit Job";
  document.getElementById("saveBtn").textContent = "Save Changes";
  toggleModeFields();
  renderJobCloudTargetControls();
  toggleScheduleFields();
  updateJobFormGate();
  scheduleCloudReadinessRefresh();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function collectFormPayload() {
  const mode = document.getElementById("mode").value;
  const scheduleType = document.getElementById("scheduleType").value;
  return {
    name: document.getElementById("name").value.trim(),
    mode,
    enabled: document.getElementById("enabled").checked,
    schedule_type: scheduleType,
    cron_expr: scheduleType === "cron" ? document.getElementById("cronExpr").value.trim() : null,
    interval_minutes: scheduleType === "interval" ? Number(document.getElementById("intervalMinutes").value) : null,
    prompt: document.getElementById("prompt").value.trim(),
    sandbox: document.getElementById("sandbox").value,
    working_directory: document.getElementById("workingDirectory").value.trim() || ".",
    timeout_seconds: Number(document.getElementById("timeoutSeconds").value),
    cloud_env_id: mode === "cloud_exec" ? currentJobCloudEnvId() : null,
    attempts: mode === "cloud_exec" ? Number(document.getElementById("attempts").value) : 1,
    codex_args: document.getElementById("codexArgs").value.trim() || null,
    env_json: document.getElementById("jobEnvJson").value.trim() || null,
    notify_email_enabled: document.getElementById("notifyEmailEnabled").checked,
    notify_email_to: document.getElementById("notifyEmailTo").value.trim() || null,
  };
}

async function submitJob(event) {
  event.preventDefault();
  const payload = collectFormPayload();
  if (!payload.name || !payload.prompt) {
    alert("Name and prompt are required.");
    return;
  }
  if (payload.mode === "cloud_exec" && payload.enabled) {
    await refreshCloudReadiness(payload.cloud_env_id, payload.working_directory);
    if (!state.cloudReadiness?.ready) {
      setConnectionError(state.cloudReadiness?.summary || "Cloud execution is not ready.");
      alert("Cloud readiness must be green before enabling a cloud_exec schedule.");
      return;
    }
  }
  try {
    if (state.editingJobId) {
      await api(`/api/jobs/${state.editingJobId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    }
  } catch (error) {
    const readiness = parseReadinessFromError(error);
    if (readiness) {
      state.cloudReadiness = readiness;
      renderCloudReadiness();
      setConnectionError(readiness.summary || "Cloud readiness check failed.");
      return;
    }
    throw error;
  }
  clearForm();
  await refreshAll();
}

async function deleteJob(id) {
  if (!confirm("Delete this job?")) return;
  await api(`/api/jobs/${id}`, { method: "DELETE" });
  await refreshAll();
}

async function toggleJob(id, enabled) {
  try {
    await api(`/api/jobs/${id}/enabled`, { method: "PATCH", body: JSON.stringify({ enabled }) });
  } catch (error) {
    const readiness = parseReadinessFromError(error);
    if (readiness) {
      state.cloudReadiness = readiness;
      renderCloudReadiness();
      setConnectionError(readiness.summary || "Cloud readiness check failed.");
      alert("Cannot enable cloud_exec job until cloud readiness is green.");
      return;
    }
    throw error;
  }
  await refreshAll();
}

async function runNow(id) {
  try {
    await api(`/api/jobs/${id}/run`, { method: "POST" });
  } catch (error) {
    const readiness = parseReadinessFromError(error);
    if (readiness) {
      state.cloudReadiness = readiness;
      renderCloudReadiness();
      setConnectionError(readiness.summary || "Cloud readiness check failed.");
      alert("Cloud run blocked until readiness check passes.");
      return;
    }
    throw error;
  }
  await refreshAll();
}

function toggleModeFields() {
  const isCloud = document.getElementById("mode").value === "cloud_exec";
  document.getElementById("cloudEnvGroup").classList.toggle("hidden", !isCloud);
  document.getElementById("cloudGateGroup").classList.toggle("hidden", !isCloud);
  document.getElementById("attemptsGroup").classList.toggle("hidden", !isCloud);
  if (isCloud) syncCloudEnvFromDefault();
  renderJobCloudTargetControls();
  updateJobFormGate();
}

function toggleScheduleFields() {
  const isCron = document.getElementById("scheduleType").value === "cron";
  document.getElementById("cronGroup").classList.toggle("hidden", !isCron);
  document.getElementById("intervalGroup").classList.toggle("hidden", isCron);
}

function toggleDeploymentPassword() {
  const needsPassword = document.getElementById("deployLogonType").value === "password";
  document.getElementById("deployPasswordGroup").classList.toggle("hidden", !needsPassword);
}

function renderSettings() {
  if (!state.settings) return;
  document.getElementById("settingsCodexExecutable").value = state.settings.codex_executable || "codex";
  document.getElementById("settingsCodexHome").value = state.settings.codex_home || "";
  document.getElementById("settingsWorkingDirectory").value = state.settings.default_working_directory || ".";
  document.getElementById("settingsNotificationsEnabled").checked = !!state.settings.notifications_enabled;
  document.getElementById("settingsDefaultNotificationTo").value = state.settings.default_notification_to || "adarnell@concepts2code.com";
  document.getElementById("settingsSmtpHost").value = state.settings.smtp_host || "";
  document.getElementById("settingsSmtpPort").value = state.settings.smtp_port || 587;
  document.getElementById("settingsSmtpSecurity").value = state.settings.smtp_security || "starttls";
  document.getElementById("settingsSmtpUsername").value = state.settings.smtp_username || "";
  document.getElementById("settingsSmtpFromEmail").value = state.settings.smtp_from_email || "";
  renderCloudTargets();
  document.getElementById("settingsDefaultCloudTargetSelect").value = state.settings.default_cloud_env_id || "";
  document.getElementById("settingsDefaultCloudEnvId").value = state.settings.default_cloud_env_id || "";
  document.getElementById("settingsApiEnvVar").value = state.settings.api_key_env_var || "OPENAI_API_KEY";
  document.getElementById("settingsGlobalEnvJson").value = state.settings.global_env_json || "";
  document.getElementById("deployTaskName").value = state.settings.deployment_task_name || "CodexSchedulerStudioHost";
  document.getElementById("deployHost").value = state.settings.deployment_host || "127.0.0.1";
  document.getElementById("deployPort").value = state.settings.deployment_port || 8787;
  document.getElementById("deployUser").value = state.settings.deployment_user || "";
  const modeLabel = state.settings.auth_mode === "api_key" ? "API key mode" : "ChatGPT/Codex account mode";
  const keyLabel = state.settings.api_key_configured ? "API key stored in keyring." : "No API key stored.";
  const smtpLabel = state.settings.smtp_password_configured ? "SMTP password stored in keyring." : "No SMTP password stored.";
  setText("settingsStatus", `${modeLabel}. ${keyLabel} ${smtpLabel}`);
  if (document.getElementById("mode").value === "cloud_exec") {
    syncCloudEnvFromDefault();
  }
}

function renderConnection() {
  if (!state.connection || !state.settings) return;
  const stateBadge = document.getElementById("connectionStateBadge");
  const meta = document.getElementById("connectionMeta");

  let badgeText = "Not connected";
  let badgeClass = "info";
  if (state.connection.rate_limited) {
    badgeText = "Rate limited";
    badgeClass = "warning";
  } else if (state.settings.last_connection_status === "ok") {
    badgeText = "Connected";
    badgeClass = "success";
  } else if (state.settings.last_connection_status === "started") {
    badgeText = "Awaiting sign-in";
    badgeClass = "info";
  } else if (state.settings.last_connection_status === "failed" || state.settings.last_connection_status === "error") {
    badgeText = "Needs attention";
    badgeClass = "danger";
  }

  stateBadge.className = `badge ${badgeClass}`;
  stateBadge.textContent = badgeText;

  const parts = [
    state.connection.installed ? "CLI installed" : "CLI missing",
    `Auth mode: ${state.settings.auth_mode === "api_key" ? "API key" : "Account"}`,
  ];
  if (state.connection.version) parts.push(`Version: ${state.connection.version}`);
  meta.textContent = parts.join(" | ");

  const connectionMessage = state.settings.last_connection_status === "ok"
    ? state.connection.error
    : (state.connection.error || state.settings.last_connection_message);
  const errorText = friendlyConnectionError(connectionMessage);
  if (errorText) {
    setConnectionError(errorText);
  } else {
    clearConnectionError();
    if (state.connection.rate_limited) {
      setConnectionHint(`Please wait ${state.connection.retry_after_seconds}s before retrying account connect.`);
    } else if (state.settings.last_connection_status === "started") {
      setConnectionHint("Complete sign-in in browser, then click Test Connection.");
    } else {
      setConnectionHint("Use Connect Account for one-click sign-in, then Test Connection.");
    }
  }

  updateConnectCooldown(state.connection.retry_after_seconds || 0);
  renderDeviceAuthCard();
  renderRuntimeDiagnostic();
}

function renderRuntimeDiagnostic() {
  const badge = document.getElementById("runtimeDiagnosticBadge");
  const summary = document.getElementById("runtimeDiagnosticSummary");
  if (!badge || !summary) return;
  const runtime = state.systemRuntime;
  if (!runtime) {
    badge.className = "badge info";
    badge.textContent = "Desktop runtime unknown";
    summary.textContent = "Checking packaged backend runtime status...";
    return;
  }
  const status = runtime.packaged_backend_status || "unavailable";
  if (status === "ok") {
    badge.className = "badge success";
    badge.textContent = "Packaged backend ready";
    summary.textContent = "Desktop packaged backend is available for local runtime checks.";
    return;
  }
  if (status === "blocked") {
    badge.className = "badge warning";
    badge.textContent = "Packaged backend blocked";
    summary.textContent = "Host policy blocked local unsigned backend execution. Local fallback parity is active; validate signed desktop artifacts in CI for release.";
    return;
  }
  badge.className = "badge info";
  badge.textContent = "Packaged backend unavailable";
  summary.textContent = `Desktop packaged backend is not active in this runtime${runtime.diagnostic_code ? ` (${runtime.diagnostic_code})` : ""}.`;
}

function renderCloudReadiness() {
  const panelBadge = document.getElementById("cloudReadyBadge");
  const panelSummary = document.getElementById("cloudReadySummary");
  const gateBadge = document.getElementById("jobCloudGateBadge");
  const envMeta = document.getElementById("cloudReadyEnvMeta");
  const resolvedMeta = document.getElementById("cloudReadyResolvedMeta");
  const wizardBadge = document.getElementById("cloudWizardBadge");
  const stepIds = ["wizardStepAccount", "wizardStepEnv", "wizardStepReady", "wizardStepLaunch"];
  const readiness = state.cloudReadiness;
  const reauthBtn = document.getElementById("cloudFixReauthBtn");
  const fallbackBtn = document.getElementById("cloudFixFallbackBtn");
  const checkBtn = document.getElementById("checkCloudReadyBtn");

  if (!readiness) {
    panelBadge.className = "badge info";
    panelBadge.textContent = "Cloud readiness unknown";
    panelSummary.textContent = "Run cloud readiness check before enabling cloud schedules.";
    envMeta.textContent = `Env source: ${currentDefaultCloudEnvId() ? "global_default" : "none"}`;
    resolvedMeta.textContent = "Resolved env: n/a";
    gateBadge.className = "badge info";
    gateBadge.textContent = "Not checked";
    wizardBadge.textContent = wizardProgressLabel(readiness);
    reauthBtn.disabled = false;
    fallbackBtn.disabled = false;
    checkBtn.disabled = false;
    stepIds.forEach((id, index) => {
      const step = document.getElementById(id);
      if (step) step.dataset.state = wizardStepState(index + 1, readiness);
    });
    updateJobFormGate();
    return;
  }

  const badgeClass = categoryToBadge(readiness.category, readiness.ready);
  const title = readiness.ready ? "Cloud ready" : `Cloud not ready (${readiness.category || "unknown"})`;
  panelBadge.className = `badge ${badgeClass}`;
  panelBadge.textContent = title;
  panelSummary.textContent = readiness.summary
    ? `${readiness.summary}${readiness.diagnostic_code ? ` (${readiness.diagnostic_code})` : ""}`
    : "";
  envMeta.textContent = `Env source: ${readiness.env_source || "none"}`;
  resolvedMeta.textContent = `Resolved env: ${readiness.resolved_cloud_env_id || "n/a"}`;

  gateBadge.className = `badge ${badgeClass}`;
  gateBadge.textContent = readiness.ready ? "Ready" : "Blocked";
  wizardBadge.textContent = wizardProgressLabel(readiness);
  const needsAuthFix = readiness.category === "auth_missing" || readiness.category === "auth_invalid";
  const needsFallback = needsAuthFix || readiness.category === "unknown";
  reauthBtn.disabled = !needsAuthFix;
  fallbackBtn.disabled = !needsFallback;
  checkBtn.disabled = false;
  stepIds.forEach((id, index) => {
    const step = document.getElementById(id);
    if (step) step.dataset.state = wizardStepState(index + 1, readiness);
  });
  updateJobFormGate();
}

function renderNotificationReadiness() {
  const badge = document.getElementById("notificationReadyBadge");
  const summary = document.getElementById("notificationReadySummary");
  if (!badge || !summary) return;
  const readiness = state.notificationReadiness;
  if (!readiness) {
    badge.className = "badge info";
    badge.textContent = "Email readiness unknown";
    summary.textContent = "Configure SMTP relay settings to enable status notifications.";
    return;
  }

  const cls = readiness.ready ? "success" : "danger";
  badge.className = `badge ${cls}`;
  badge.textContent = readiness.ready ? "Email ready" : `Email not ready (${readiness.category || "unknown"})`;
  summary.textContent = readiness.summary || "";
}

function updateConnectButtonState() {
  const btn = document.getElementById("connectAccountBtn");
  if (!btn) return;
  if (connectCooldownSeconds > 0) {
    btn.disabled = true;
    btn.textContent = `Connect Account (${connectCooldownSeconds}s)`;
    return;
  }
  btn.disabled = false;
  btn.textContent = "Connect Account";
}

function updateConnectCooldown(seconds) {
  connectCooldownSeconds = Math.max(0, Number(seconds || 0));
  if (connectCooldownTimer) {
    clearInterval(connectCooldownTimer);
    connectCooldownTimer = null;
  }
  updateConnectButtonState();
  if (connectCooldownSeconds <= 0) return;
  connectCooldownTimer = setInterval(() => {
    connectCooldownSeconds = Math.max(0, connectCooldownSeconds - 1);
    updateConnectButtonState();
    if (connectCooldownSeconds <= 0 && connectCooldownTimer) {
      clearInterval(connectCooldownTimer);
      connectCooldownTimer = null;
      refreshConnection().catch(() => {});
    }
  }, 1000);
}

function renderPreflight() {
  const badge = document.getElementById("preflightBadge");
  if (!state.preflight) {
    badge.className = "badge info";
    badge.textContent = "runtime unknown";
    return;
  }
  badge.className = `badge ${statusBadgeClass(state.preflight.status)}`;
  const failing = state.preflight.checks.filter((c) => c.status === "error").length;
  badge.textContent = failing ? `runtime issues: ${failing}` : "runtime ready";
}

async function refreshSettings() {
  state.settings = await api("/api/settings");
  renderSettings();
  renderConnection();
  renderCloudReadiness();
  renderNotificationReadiness();
}

async function refreshSystemRuntime() {
  state.systemRuntime = await api("/api/system/runtime");
  renderRuntimeDiagnostic();
}

async function refreshNotificationReadiness() {
  state.notificationReadiness = await api("/api/notifications/readiness");
  renderNotificationReadiness();
}

async function refreshCloudTargets() {
  const workingDirectory = (document.getElementById("settingsWorkingDirectory")?.value || ".").trim() || ".";
  const result = await api(`/api/cloud/targets?working_directory=${encodeURIComponent(workingDirectory)}`);
  state.cloudTargets = result.targets || [];
  renderCloudTargets();
}

async function submitSettings(event) {
  event.preventDefault();
  const payload = {
    codex_executable: document.getElementById("settingsCodexExecutable").value.trim() || "codex",
    codex_home: document.getElementById("settingsCodexHome").value.trim() || null,
    default_working_directory: document.getElementById("settingsWorkingDirectory").value.trim() || ".",
    default_cloud_env_id: currentDefaultCloudEnvId(),
    api_key_env_var: document.getElementById("settingsApiEnvVar").value.trim() || "OPENAI_API_KEY",
    global_env_json: document.getElementById("settingsGlobalEnvJson").value.trim() || null,
    deployment_task_name: document.getElementById("deployTaskName").value.trim() || null,
    deployment_host: document.getElementById("deployHost").value.trim() || "127.0.0.1",
    deployment_port: Number(document.getElementById("deployPort").value || 8787),
    deployment_user: document.getElementById("deployUser").value.trim() || null,
    auth_mode: state.settings?.auth_mode || "chatgpt_account",
    smtp_host: document.getElementById("settingsSmtpHost").value.trim() || null,
    smtp_port: Number(document.getElementById("settingsSmtpPort").value || 587),
    smtp_security: document.getElementById("settingsSmtpSecurity").value || "starttls",
    smtp_username: document.getElementById("settingsSmtpUsername").value.trim() || null,
    smtp_from_email: document.getElementById("settingsSmtpFromEmail").value.trim() || null,
    notifications_enabled: document.getElementById("settingsNotificationsEnabled").checked,
    default_notification_to: document.getElementById("settingsDefaultNotificationTo").value.trim() || null,
  };
  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });

  const smtpPassword = document.getElementById("settingsSmtpPassword").value.trim();
  if (smtpPassword) {
    await api("/api/settings/smtp-password", { method: "POST", body: JSON.stringify({ password: smtpPassword }) });
    document.getElementById("settingsSmtpPassword").value = "";
  }

  const apiKey = document.getElementById("settingsApiKey").value.trim();
  if (apiKey) {
    await api("/api/settings/api-key", { method: "POST", body: JSON.stringify({ api_key: apiKey }) });
    document.getElementById("settingsApiKey").value = "";
  }
  await refreshSettings();
  await refreshConnection();
  await refreshPreflight();
  await refreshCloudReadiness();
  await refreshNotificationReadiness();
  setText("settingsStatus", "Settings saved.");
}

async function clearApiKey() {
  await api("/api/settings/api-key", { method: "DELETE" });
  await refreshSettings();
  setText("settingsStatus", "API key cleared.");
}

async function clearSmtpPassword() {
  await api("/api/settings/smtp-password", { method: "DELETE" });
  await refreshSettings();
  await refreshNotificationReadiness();
  setText("settingsStatus", "SMTP password cleared.");
}

async function setConnectionMode(authMode) {
  await api("/api/connection/mode", { method: "POST", body: JSON.stringify({ auth_mode: authMode }) });
  await refreshSettings();
  await refreshConnection();
  await refreshCloudReadiness();
}

async function refreshConnection() {
  state.connection = await api("/api/connection/status");
  renderConnection();
}

async function startDeviceAuth() {
  await setConnectionMode("chatgpt_account");
  clearConnectionError();
  setConnectionHint("Requesting secure sign-in link...");
  let result;
  try {
    result = await api("/api/connection/device-auth/start", { method: "POST" });
  } catch (error) {
    if (error.status === 429) {
      const retrySeconds = Number(error.payload?.detail?.retry_after_seconds || 60);
      updateConnectCooldown(retrySeconds);
      setConnectionHint(`Rate limited. Retry in ${retrySeconds} seconds.`);
      await refreshSettings();
      await refreshConnection();
      return;
    }
    setConnectionError(`Connection start failed: ${error.message || "Unknown error"}`);
    setConnectionHint("");
    return;
  }
  if (!result.ok) {
    const msg = result.error || result.raw_output || "Unknown error";
    setConnectionError(`Connection start failed: ${friendlyConnectionError(msg) || "Unknown error"}`);
    setConnectionHint("");
    return;
  }
  const expirySeconds = parseExpiryFromText(result.raw_output) || 15 * 60;
  state.deviceAuth = {
    verificationUrl: result.verification_url || "",
    userCode: result.user_code || "",
    expiresAt: Date.now() + expirySeconds * 1000,
  };
  renderDeviceAuthCard();
  setConnectionHint("Sign in with your account, then click Test Connection.");
  if (result.verification_url) {
    window.open(result.verification_url, "_blank", "noopener,noreferrer");
  }
  await refreshSettings();
  await refreshConnection();
  await refreshCloudReadiness();
}

async function runConnectionTest() {
  const result = await api("/api/connection/test", { method: "POST" });
  if (result.ok) {
    setConnectionHint("Connection test passed.");
    clearConnectionError();
    state.deviceAuth = null;
    renderDeviceAuthCard();
  } else {
    const msg = friendlyConnectionError(result.output || result.message || "No output");
    setConnectionError(`Connection test failed: ${msg}`);
    setConnectionHint("");
  }
  await refreshSettings();
  await refreshConnection();
}

async function refreshPreflight() {
  state.preflight = await api("/api/preflight");
  renderPreflight();
}

function currentCloudInputs() {
  const mode = document.getElementById("mode").value;
  const settingsWorkingDirectory = (document.getElementById("settingsWorkingDirectory")?.value || state.settings?.default_working_directory || ".").trim() || ".";
  const workingDirectory = (document.getElementById("workingDirectory").value || settingsWorkingDirectory).trim() || ".";
  if (mode !== "cloud_exec") {
    return {
      cloudEnvId: currentDefaultCloudEnvId(),
      workingDirectory: settingsWorkingDirectory,
    };
  }
  return {
    cloudEnvId: currentJobCloudEnvId(),
    workingDirectory,
  };
}

async function resolveCloudWizardStuckState() {
  clearConnectionError();
  setConnectionHint("Refreshing cloud targets and re-running readiness check...");
  await refreshCloudTargets();
  await refreshCloudReadiness();
  const readiness = state.cloudReadiness;
  if (readiness?.ready) {
    setConnectionHint("Cloud wizard is ready. You can enable cloud schedules.");
    return;
  }
  const reason = `${readiness?.category || "unknown"}${readiness?.diagnostic_code ? `/${readiness.diagnostic_code}` : ""}`;
  const summary = readiness?.summary || "Cloud readiness remains blocked.";
  setConnectionError(`Cloud readiness blocked (${reason}): ${summary}`);
}

async function refreshCloudReadiness(cloudEnvId = null, workingDirectory = null) {
  const query = new URLSearchParams();
  const inputs = currentCloudInputs();
  const envToUse = cloudEnvId ?? inputs.cloudEnvId;
  const wdToUse = workingDirectory ?? inputs.workingDirectory;
  if (envToUse) query.set("cloud_env_id", envToUse);
  if (wdToUse) query.set("working_directory", wdToUse);
  const suffix = query.size ? `?${query.toString()}` : "";
  state.cloudReadiness = await api(`/api/cloud/readiness${suffix}`);
  renderCloudReadiness();
  updateJobFormGate();
}

function openVerificationLink() {
  const url = state.deviceAuth?.verificationUrl;
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

async function copyDeviceCode() {
  const code = state.deviceAuth?.userCode;
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code);
    setConnectionHint("Code copied. Paste it into the sign-in page.");
  } catch {
    setConnectionError("Could not copy code automatically. Copy it manually from the card.");
  }
}

function applySmtpPreset() {
  const preset = document.getElementById("settingsSmtpPreset").value;
  if (preset === "sendgrid") {
    document.getElementById("settingsSmtpHost").value = "smtp.sendgrid.net";
    document.getElementById("settingsSmtpPort").value = "587";
    document.getElementById("settingsSmtpSecurity").value = "starttls";
    if (!document.getElementById("settingsSmtpUsername").value.trim()) {
      document.getElementById("settingsSmtpUsername").value = "apikey";
    }
    setText("notificationStatus", "SendGrid preset applied.");
    return;
  }
  if (preset === "ses") {
    document.getElementById("settingsSmtpHost").value = "email-smtp.us-east-1.amazonaws.com";
    document.getElementById("settingsSmtpPort").value = "587";
    document.getElementById("settingsSmtpSecurity").value = "starttls";
    setText("notificationStatus", "AWS SES preset applied (adjust region host if needed).");
    return;
  }
  setText("notificationStatus", "Custom SMTP mode.");
}

async function sendTestEmail() {
  const recipient = document.getElementById("settingsDefaultNotificationTo").value.trim() || null;
  try {
    const response = await api("/api/notifications/test", {
      method: "POST",
      body: JSON.stringify({ recipient }),
    });
    setText("notificationStatus", `Test email sent to ${response.recipient}.`);
  } catch (error) {
    setText("notificationStatus", `Test email failed: ${error.message}`);
  }
  await refreshNotificationReadiness();
}

function deploymentPayload() {
  return {
    task_name: document.getElementById("deployTaskName").value.trim(),
    host: document.getElementById("deployHost").value.trim() || "127.0.0.1",
    port: Number(document.getElementById("deployPort").value || 8787),
    python_path: document.getElementById("deployPythonPath").value.trim() || "python",
    user: document.getElementById("deployUser").value.trim(),
    logon_type: document.getElementById("deployLogonType").value,
    password: document.getElementById("deployPassword").value.trim() || null,
    run_level: document.getElementById("deployRunLevel").value,
    codex_scheduler_db: null,
    codex_scheduler_disable_autostart: false,
  };
}

async function submitDeployment(event) {
  event.preventDefault();
  const payload = deploymentPayload();
  if (!payload.task_name || !payload.user) {
    alert("Task name and run-as user are required.");
    return;
  }
  const response = await api("/api/deployment/install", { method: "POST", body: JSON.stringify(payload) });
  setText("deploymentStatus", `Installed: ${response.task_name}`);
  await refreshSettings();
}

async function removeDeployment() {
  const taskName = document.getElementById("deployTaskName").value.trim();
  if (!taskName) return;
  if (!confirm(`Remove scheduled task '${taskName}'?`)) return;
  const response = await api(`/api/deployment/${encodeURIComponent(taskName)}`, { method: "DELETE" });
  setText("deploymentStatus", `Remove status: ${response.status}`);
  await refreshSettings();
}

async function checkDeployment() {
  const taskName = document.getElementById("deployTaskName").value.trim();
  if (!taskName) return;
  const response = await api(`/api/deployment/${encodeURIComponent(taskName)}`);
  if (!response.exists) {
    setText("deploymentStatus", "Task not found.");
  } else {
    setText("deploymentStatus", `Task state: ${response.state}`);
  }
}

async function runWindowsAction(path, method, successPrefix) {
  try {
    const response = await api(path, { method });
    setText("windowsStatus", `${successPrefix}: ${response.message || "ok"}`);
  } catch (error) {
    setText("windowsStatus", `${successPrefix} failed: ${error.message}`);
  }
}

async function installWindowsAppMode() {
  await runWindowsAction("/api/windows/app-mode/install", "POST", "Install");
}

async function uninstallWindowsAppMode() {
  await runWindowsAction("/api/windows/app-mode/install", "DELETE", "Uninstall");
}

async function startWindowsHost() {
  await runWindowsAction("/api/windows/host/start", "POST", "Start host");
}

async function stopWindowsHost() {
  await runWindowsAction("/api/windows/host/stop", "POST", "Stop host");
}

async function refreshJobs() {
  state.jobs = await api("/api/jobs");
  renderJobs();
}

async function refreshRuns() {
  state.runs = await api("/api/runs?limit=100");
  renderRuns();
}

async function refreshHealth() {
  const health = await api("/api/health");
  const badge = document.getElementById("healthBadge");
  badge.className = `badge ${statusBadgeClass(health.status)}`;
  badge.textContent = `${health.status} @ ${new Date(health.time).toLocaleTimeString()}`;
}

async function refreshAll() {
  await refreshSettings();
  await Promise.all([
    refreshJobs(),
    refreshRuns(),
    refreshHealth(),
    refreshConnection(),
    refreshSystemRuntime(),
    refreshPreflight(),
    refreshCloudTargets(),
    refreshCloudReadiness(),
    refreshNotificationReadiness(),
  ]);
}

function wireEvents() {
  document.getElementById("jobForm").addEventListener("submit", submitJob);
  document.getElementById("resetFormBtn").addEventListener("click", clearForm);
  document.getElementById("refreshAllBtn").addEventListener("click", refreshAll);
  document.getElementById("refreshRunsBtn").addEventListener("click", refreshRuns);
  document.getElementById("jobSearch").addEventListener("input", renderJobs);
  document.getElementById("mode").addEventListener("change", toggleModeFields);
  document.getElementById("mode").addEventListener("change", () => {
    updateJobFormGate();
    scheduleCloudReadinessRefresh();
  });
  document.getElementById("scheduleType").addEventListener("change", toggleScheduleFields);
  document.getElementById("jobUseDefaultCloudTarget").addEventListener("change", () => {
    renderJobCloudTargetControls();
    updateJobFormGate();
    scheduleCloudReadinessRefresh();
  });
  document.getElementById("jobCloudTargetSelect").addEventListener("change", () => {
    document.getElementById("jobCloudTargetManual").value = "";
    updateJobFormGate();
    scheduleCloudReadinessRefresh();
  });
  document.getElementById("jobCloudTargetManual").addEventListener("input", () => {
    updateJobFormGate();
    scheduleCloudReadinessRefresh();
  });
  document.getElementById("workingDirectory").addEventListener("input", () => {
    updateJobFormGate();
    scheduleCloudReadinessRefresh();
  });
  document.getElementById("enabled").addEventListener("change", updateJobFormGate);
  document.getElementById("notifyEmailEnabled").addEventListener("change", () => {
    const enabled = document.getElementById("notifyEmailEnabled").checked;
    document.getElementById("notifyEmailToGroup").classList.toggle("hidden", !enabled);
  });

  document.getElementById("settingsForm").addEventListener("submit", submitSettings);
  document.getElementById("reloadSettingsBtn").addEventListener("click", refreshSettings);
  document.getElementById("clearApiKeyBtn").addEventListener("click", clearApiKey);
  document.getElementById("clearSmtpPasswordBtn").addEventListener("click", clearSmtpPassword);
  document.getElementById("settingsSmtpPreset").addEventListener("change", applySmtpPreset);
  document.getElementById("refreshNotificationReadyBtn").addEventListener("click", refreshNotificationReadiness);
  document.getElementById("sendTestEmailBtn").addEventListener("click", sendTestEmail);
  document.getElementById("settingsDefaultCloudTargetSelect").addEventListener("change", () => {
    document.getElementById("settingsDefaultCloudEnvId").value = "";
    if (document.getElementById("mode").value === "cloud_exec") {
      syncCloudEnvFromDefault();
      scheduleCloudReadinessRefresh();
      updateJobFormGate();
    }
    renderCloudReadiness();
  });
  document.getElementById("settingsDefaultCloudEnvId").addEventListener("input", () => {
    if (document.getElementById("mode").value === "cloud_exec") {
      syncCloudEnvFromDefault();
      scheduleCloudReadinessRefresh();
      updateJobFormGate();
    }
    renderCloudReadiness();
  });
  document.getElementById("settingsWorkingDirectory").addEventListener("change", async () => {
    await refreshCloudTargets();
    await refreshCloudReadiness();
  });
  document.getElementById("connectAccountBtn").addEventListener("click", startDeviceAuth);
  document.getElementById("testConnectionBtn").addEventListener("click", runConnectionTest);
  document.getElementById("refreshConnectionBtn").addEventListener("click", refreshConnection);
  document.getElementById("checkCloudReadyBtn").addEventListener("click", () => refreshCloudReadiness());
  document.getElementById("refreshCloudTargetsBtn").addEventListener("click", refreshCloudTargets);
  document.getElementById("cloudResolveStuckBtn").addEventListener("click", resolveCloudWizardStuckState);
  document.getElementById("refreshCloudTargetsInlineBtn").addEventListener("click", refreshCloudTargets);
  document.getElementById("jobCloudGateBtn").addEventListener("click", () => refreshCloudReadiness());
  document.getElementById("cloudFixReauthBtn").addEventListener("click", startDeviceAuth);
  document.getElementById("cloudFixFallbackBtn").addEventListener("click", openFallbackPanel);
  document.getElementById("openVerificationBtn").addEventListener("click", openVerificationLink);
  document.getElementById("copyDeviceCodeBtn").addEventListener("click", copyDeviceCode);
  document.getElementById("useAccountModeBtn").addEventListener("click", () => setConnectionMode("chatgpt_account"));
  document.getElementById("useApiModeBtn").addEventListener("click", () => setConnectionMode("api_key"));

  document.getElementById("deploymentForm").addEventListener("submit", submitDeployment);
  document.getElementById("removeDeploymentBtn").addEventListener("click", removeDeployment);
  document.getElementById("checkDeploymentBtn").addEventListener("click", checkDeployment);
  document.getElementById("deployLogonType").addEventListener("change", toggleDeploymentPassword);
  document.getElementById("windowsInstallBtn").addEventListener("click", installWindowsAppMode);
  document.getElementById("windowsUninstallBtn").addEventListener("click", uninstallWindowsAppMode);
  document.getElementById("windowsStartHostBtn").addEventListener("click", startWindowsHost);
  document.getElementById("windowsStopHostBtn").addEventListener("click", stopWindowsHost);
}

async function init() {
  wireEvents();
  clearForm();
  toggleDeploymentPassword();
  updateJobFormGate();
  renderCloudReadiness();
  renderNotificationReadiness();
  try {
    await refreshAll();
  } catch (error) {
    console.error(error);
    alert(`Failed to load data: ${error.message}`);
  }
}

init();
