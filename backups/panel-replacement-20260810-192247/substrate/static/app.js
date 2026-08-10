let activePayloadJobId = null;
let payloadJobTimer = null;

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.style.background = isError ? "#6a1d14" : "#0d2b24";
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3200);
}

function setNetworkBanner(message, isError = false) {
  const banner = document.getElementById("network-banner");
  if (!banner) return;
  banner.textContent = message;
  banner.classList.toggle("banner--error", isError);
  banner.classList.toggle("hidden", !message);
}

function setPanelStatus(label, good = true) {
  const status = document.getElementById("panel-status");
  if (!status) return;
  status.textContent = label;
  status.classList.toggle("status-pill--good", good);
  status.classList.toggle("status-pill--bad", !good);
  status.classList.toggle("status-pill--warn", false);
}

function setLastRefresh(label) {
  const lastRefresh = document.getElementById("panel-last-refresh");
  if (!lastRefresh) return;
  lastRefresh.textContent = label;
}

function setPayloadJobStatus(message, isError = false) {
  const status = document.getElementById("payload-job-status");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("status-text--error", isError);
  status.classList.toggle("status-text--good", !isError);
}

function buildFormData(form) {
  const data = new FormData(form);
  form.querySelectorAll('input[type="checkbox"]').forEach((box) => {
    data.set(box.name, box.checked ? "true" : "false");
  });
  return data;
}

function setFormBusy(form, busy) {
  form.querySelectorAll("input, select, button").forEach((field) => {
    field.disabled = busy;
  });
}

function payloadErrorMessage(payload, fallback = "Action failed") {
  if (!payload) return fallback;
  if (payload.error && payload.error.message) return payload.error.message;
  if (payload.detail) return payload.detail;
  if (payload.message) return payload.message;
  return fallback;
}

function renderRuns(runs) {
  const tbody = document.querySelector("#runs-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!runs.length) {
    tbody.innerHTML =
      '<tr><td colspan="7" class="empty-state">No runs yet. Start a chain or task to generate history.</td></tr>';
    return;
  }
  runs.slice(0, 30).forEach((run) => {
    const statusClass =
      run.status === "success" ? "good" : run.status === "running" ? "warn" : "bad";
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="mono">${run.started_at || "-"}</span></td>
      <td>${run.run_type || "-"}</td>
      <td><span class="mono">${run.repo_slug || "-"}</span></td>
      <td><span class="status-pill status-pill--${statusClass}">${run.status || "-"}</span></td>
      <td>${run.stage || "-"}</td>
      <td>${run.mode || "-"}</td>
      <td><a href="/runs/${run.run_id}">details</a></td>
    `;
    tbody.appendChild(row);
  });
}

function renderMetrics(metrics) {
  const runs = document.getElementById("metric-runs");
  const successRate = document.getElementById("metric-success-rate");
  const successBar = document.getElementById("metric-success-bar");
  const repos = document.getElementById("metric-repos");
  const sources = document.getElementById("metric-sources");
  if (runs) runs.textContent = metrics.runs_total ?? 0;
  if (successRate) successRate.textContent = `${metrics.success_rate ?? 0}%`;
  if (successBar) successBar.style.width = `${metrics.success_rate ?? 0}%`;
  if (repos) repos.textContent = metrics.repositories_total ?? 0;
  if (sources) sources.textContent = metrics.sources_total ?? 0;
}

function renderPayloads(payloads) {
  const select = document.getElementById("payload-id-select");
  if (!select) return;
  const previous = select.value;
  select.innerHTML = "";
  if (!payloads.length) {
    select.innerHTML = '<option value="">No payloads available</option>';
    return;
  }
  payloads.forEach((payload) => {
    const option = document.createElement("option");
    option.value = payload.id;
    option.textContent = payload.name;
    if (!payload.available) {
      option.textContent = `${payload.name} (needs repo)`;
    }
    select.appendChild(option);
  });
  const hasPrevious = payloads.some((item) => item.id === previous);
  if (hasPrevious) select.value = previous;
}

function renderStandards(summary, tracks) {
  const countNode = document.getElementById("standards-count");
  const trackNode = document.getElementById("standards-tracks");
  if (countNode) countNode.textContent = summary.standards_total ?? 0;
  if (trackNode) trackNode.textContent = summary.tracks_total ?? 0;

  const tbody = document.querySelector("#standards-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  const rows = [];
  tracks.forEach((track) => {
    (track.standards || []).forEach((standard) => {
      rows.push({ track: track.name, standard });
    });
  });
  if (!rows.length) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="empty-state">No standards catalog loaded. Add entries in standards.yaml.</td></tr>';
    return;
  }
  rows.forEach((rowData) => {
    const row = document.createElement("tr");
    const source = rowData.standard.source_url || rowData.standard.repo_url || "-";
    row.innerHTML = `
      <td>${rowData.track}</td>
      <td>${rowData.standard.name}</td>
      <td>${rowData.standard.format}</td>
      <td>${rowData.standard.maintained_by}</td>
      <td class="truncate">${
        source === "-" ? "-" : `<a href="${source}" target="_blank" rel="noopener">${source}</a>`
      }</td>
    `;
    tbody.appendChild(row);
  });
}

function renderTooling(tooling) {
  const managerNode = document.getElementById("tooling-managers");
  const availableManagers = tooling.available_managers || [];
  if (managerNode) {
    managerNode.textContent = `Available package managers: ${
      availableManagers.length ? availableManagers.join(", ") : "none detected"
    }`;
  }

  const profileSelect = document.getElementById("deps-profile-select");
  if (profileSelect) {
    const previous = profileSelect.value;
    profileSelect.innerHTML = '<option value="">(none)</option>';
    (tooling.profiles || []).forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = profile.name;
      profileSelect.appendChild(option);
    });
    const hasPrevious = (tooling.profiles || []).some((profile) => profile.id === previous);
    if (hasPrevious) profileSelect.value = previous;
  }

  const tbody = document.querySelector("#tooling-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  const profiles = tooling.profiles || [];
  if (!profiles.length) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="empty-state">No tool profile catalog loaded. Add entries in tool_profiles.yaml.</td></tr>';
    return;
  }
  profiles.forEach((profile) => {
    (profile.tools || []).forEach((tool) => {
      const row = document.createElement("tr");
      const statusClass = tool.installed ? "good" : "warn";
      const installHint = tool.install_commands && tool.install_commands.length
        ? tool.install_commands[0]
        : "-";
      row.innerHTML = `
        <td>${profile.name}</td>
        <td>${tool.name}</td>
        <td><span class="mono">${tool.binary}</span></td>
        <td><span class="status-pill status-pill--${statusClass}">${tool.installed ? "installed" : "missing"}</span></td>
        <td class="truncate"><span class="mono">${installHint}</span></td>
      `;
      tbody.appendChild(row);
    });
  });
}

function setSelectOptions(selectId, options, includeEmpty = false) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const previous = select.value;
  select.innerHTML = includeEmpty ? '<option value="">(none)</option>' : "";
  options.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  });
  const hasPrevious = options.some((item) => item.value === previous);
  if (hasPrevious) select.value = previous;
}

function renderIntegrations(integrations) {
  const services = integrations.services || [];
  const serviceOptions = services.map((service) => ({
    value: service.id,
    label: service.name,
  }));
  setSelectOptions("integration-service-select", serviceOptions);
  setSelectOptions("integration-disconnect-select", serviceOptions);

  const tbody = document.querySelector("#integrations-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!services.length) {
    tbody.innerHTML =
      '<tr><td colspan="9" class="empty-state">No integration catalog loaded. Add entries in integrations.yaml.</td></tr>';
    return;
  }
  services.forEach((service) => {
    const row = document.createElement("tr");
    const connectedClass = service.connected ? "good" : "muted";
    const modeClass = service.mode === "write" ? "warn" : "good";
    const scopes = (service.granted_scopes || []).join(", ") || "-";
    const loginLink = service.auth && service.auth.login_url
      ? `<a href="${service.auth.login_url}" target="_blank" rel="noopener">login</a>`
      : "-";
    const docsLink = service.auth && service.auth.docs_url
      ? `<a href="${service.auth.docs_url}" target="_blank" rel="noopener">docs</a>`
      : "";
    row.innerHTML = `
      <td>${service.name}</td>
      <td>${service.availability || "-"}</td>
      <td>${service.api_status || "-"}</td>
      <td><span class="status-pill status-pill--${connectedClass}">${service.connected ? "yes" : "no"}</span></td>
      <td><span class="status-pill status-pill--${modeClass}">${service.mode || "read"}</span></td>
      <td class="truncate">${scopes}</td>
      <td>${service.auth_method || "-"}</td>
      <td class="truncate">${loginLink}${docsLink ? ` | ${docsLink}` : ""}</td>
      <td class="truncate">${service.notes || "-"}</td>
    `;
    tbody.appendChild(row);
  });
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return null;
}

function dotfileChecksumLabel(item) {
  const data = item || {};
  const checksum = firstDefined(data.checksum, data.sha256, data.digest, data.fingerprint);
  if (data.changed === true || data.modified === true || data.status === "changed") {
    return { label: "changed", kind: "warn" };
  }
  if (typeof data.changed === "string" && data.changed) {
    return { label: data.changed, kind: "warn" };
  }
  if (checksum) {
    return { label: String(checksum).slice(0, 16), kind: "good" };
  }
  return { label: data.status || "-", kind: data.status === "unchanged" ? "good" : "muted" };
}

function renderDotfilesPreview(dotfiles) {
  const preview = document.getElementById("dotfiles-preview");
  if (!preview) return;
  const plan = firstDefined(dotfiles.plan, dotfiles.preview, dotfiles.deploy_plan, dotfiles.result);
  if (Array.isArray(plan)) {
    preview.innerHTML = `
      <div class="dotfiles-preview-head">Plan preview</div>
      <ul class="dotfiles-preview-list">
        ${plan
          .slice(0, 8)
          .map((item) => `<li>${typeof item === "string" ? item : JSON.stringify(item)}</li>`)
          .join("")}
      </ul>
    `;
    return;
  }
  if (plan && typeof plan === "object") {
    const lines = Object.entries(plan)
      .slice(0, 8)
      .map(([key, value]) => `<li><span class="mono">${key}</span>: ${typeof value === "string" ? value : JSON.stringify(value)}</li>`)
      .join("");
    preview.innerHTML = `
      <div class="dotfiles-preview-head">Plan preview</div>
      <ul class="dotfiles-preview-list">${lines}</ul>
    `;
    return;
  }
  if (typeof plan === "string" && plan.trim()) {
    preview.textContent = plan;
    return;
  }
  preview.textContent = "Select a target and generate a plan to preview deployment steps.";
}

function renderDotfiles(dotfiles, options = {}) {
  const summary = dotfiles.summary || {};
  let entries = [];
  for (const candidate of [
    dotfiles.entries,
    dotfiles.inventory,
    dotfiles.items,
    dotfiles.records,
    dotfiles.files,
    dotfiles.dotfiles,
  ]) {
    if (Array.isArray(candidate)) {
      entries = candidate;
      break;
    }
  }
  const tbody = document.querySelector("#dotfiles-table tbody");
  if (tbody) {
    tbody.innerHTML = "";
    if (!entries.length) {
      tbody.innerHTML =
        '<tr><td colspan="4" class="empty-state">No configs loaded yet. Run scan to populate the inventory.</td></tr>';
    } else {
      entries.forEach((item) => {
        const checksum = dotfileChecksumLabel(item);
        const row = document.createElement("tr");
        row.innerHTML = `
          <td class="truncate"><span class="mono">${item.path || item.source_path || item.name || "-"}</span></td>
          <td>${item.type || item.kind || item.file_type || "-"}</td>
          <td><span class="status-pill status-pill--${checksum.kind}">${checksum.label}</span></td>
          <td>${item.last_backup || item.last_backup_at || item.backed_up_at || "-"}</td>
        `;
        tbody.appendChild(row);
      });
    }
  }

  const total = document.getElementById("dotfiles-total");
  const changed = document.getElementById("dotfiles-changed");
  const backedUp = document.getElementById("dotfiles-backed-up");
  if (total) {
    total.textContent = `${firstDefined(
      summary.entries_total,
      summary.total,
      summary.count,
      summary.inventory_total,
      entries.length,
      0,
    )} items`;
  }
  if (changed) {
    changed.textContent = `${firstDefined(
      summary.changed,
      summary.modified,
      summary.changed_total,
      summary.modified_total,
      0,
    )} changed`;
  }
  if (backedUp) {
    backedUp.textContent = `${firstDefined(
      summary.backed_up_total,
      summary.backed_up,
      summary.backup_total,
      summary.backup_count,
      0,
    )} backed up`;
  }

  const targetSelect = document.getElementById("dotfiles-target-env");
  const targetValue = firstDefined(dotfiles.target_env, dotfiles.target, summary.target_env, summary.target);
  if (targetSelect && targetValue) {
    targetSelect.value = targetValue;
  }
  const lineEndings = document.getElementById("dotfiles-line-endings");
  const lineEndingValue = firstDefined(
    dotfiles.line_endings,
    dotfiles.line_endings_mode,
    summary.line_endings,
    summary.line_endings_mode,
  );
  if (lineEndings && lineEndingValue) {
    lineEndings.value = lineEndingValue;
  }
  const conversionMode = document.getElementById("dotfiles-conversion-mode");
  const conversionValue = firstDefined(
    dotfiles.conversion_mode,
    dotfiles.conversion,
    summary.conversion_mode,
    summary.conversion,
  );
  if (conversionMode && conversionValue) {
    conversionMode.value = conversionValue;
  }
  const profileSelect = document.getElementById("dotfiles-profile");
  if (profileSelect) {
    const previous = profileSelect.value;
    const profiles = Array.isArray(dotfiles.catalog?.profiles) ? dotfiles.catalog.profiles : [];
    profileSelect.innerHTML = '<option value="">all profiles</option>';
    profiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = profile.name || profile.id;
      profileSelect.appendChild(option);
    });
    if (previous && profiles.some((profile) => profile.id === previous)) {
      profileSelect.value = previous;
    }
  }

  const status = document.getElementById("dotfiles-status");
  if (status) {
    if (options.statusText) {
      status.textContent = options.statusText;
    } else {
      const lastUpdated = firstDefined(
        dotfiles.updated_at,
        dotfiles.last_scan_at,
        dotfiles.last_scanned_at,
        summary.updated_at,
        summary.last_scan_at,
        summary.last_scanned_at,
      );
      status.textContent = lastUpdated
        ? `Backup & Sync updated ${lastUpdated}`
        : "Backup & Sync inventory loaded.";
    }
  }

  renderDotfilesPreview(dotfiles);
}

function renderLearning(learning) {
  const knownGoodBody = document.querySelector("#known-good-table tbody");
  if (knownGoodBody) {
    knownGoodBody.innerHTML = "";
    const knownGood = learning.known_good || [];
    if (!knownGood.length) {
      knownGoodBody.innerHTML =
        '<tr><td colspan="5" class="empty-state">No known-good commands recorded yet.</td></tr>';
    } else {
      knownGood.forEach((item) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td class="truncate"><span class="mono">${item.command || "-"}</span></td>
          <td>${item.success_count || 0}</td>
          <td>${item.repo_slug || "-"}</td>
          <td>${item.stage || "-"}</td>
          <td>${item.last_success_at || "-"}</td>
        `;
        knownGoodBody.appendChild(row);
      });
    }
  }

  const errorBody = document.querySelector("#error-index-table tbody");
  if (errorBody) {
    errorBody.innerHTML = "";
    const errors = learning.errors || [];
    if (!errors.length) {
      errorBody.innerHTML =
        '<tr><td colspan="5" class="empty-state">No recurring error signatures recorded.</td></tr>';
    } else {
      errors.forEach((item) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td><span class="mono">${item.signature || "-"}</span></td>
          <td>${item.count || 0}</td>
          <td>${item.last_seen || "-"}</td>
          <td class="truncate"><span class="mono">${item.command || "-"}</span></td>
          <td class="truncate">${item.error_snippet || "-"}</td>
        `;
        errorBody.appendChild(row);
      });
    }
  }
}

async function pollPayloadJob(jobId) {
  if (!jobId) return;
  try {
    const response = await fetch(`/api/payload-jobs/${jobId}`, { cache: "no-store" });
    if (!response.ok) {
      setPayloadJobStatus(`Payload job ${jobId.slice(0, 10)} unavailable`, true);
      return;
    }
    const job = await response.json();
    const prefix = `${job.payload_name || job.payload_id} (${job.job_id.slice(0, 10)})`;
    if (job.status === "success") {
      setPayloadJobStatus(`${prefix}: success`, false);
      if (payloadJobTimer) clearInterval(payloadJobTimer);
      payloadJobTimer = null;
      activePayloadJobId = null;
      refreshDashboard();
      return;
    }
    if (job.status === "failed") {
      setPayloadJobStatus(`${prefix}: failed${job.error ? ` | ${job.error}` : ""}`, true);
      if (payloadJobTimer) clearInterval(payloadJobTimer);
      payloadJobTimer = null;
      activePayloadJobId = null;
      refreshDashboard();
      return;
    }
    setPayloadJobStatus(`${prefix}: ${job.status}`, false);
  } catch (error) {
    setPayloadJobStatus(`Payload job polling failed: ${error}`, true);
  }
}

async function refreshDotfiles() {
  try {
    const response = await fetch("/api/config-sync", { cache: "no-store" });
    if (!response.ok) {
      renderDotfiles({}, { statusText: "Backup & Sync API unavailable." });
      return;
    }
    const payload = await response.json();
    renderDotfiles(payload || {});
  } catch {
    renderDotfiles({}, { statusText: "Backup & Sync refresh failed." });
  }
}

function trackPayloadJob(jobId) {
  activePayloadJobId = jobId;
  if (payloadJobTimer) clearInterval(payloadJobTimer);
  payloadJobTimer = setInterval(() => {
    if (!activePayloadJobId) return;
    pollPayloadJob(activePayloadJobId);
  }, 2200);
  pollPayloadJob(jobId);
}

async function submitActionForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const endpoint = event.submitter?.dataset.endpoint || form.dataset.endpoint;
  if (!endpoint) return;
  if (endpoint.includes("/api/config-sync/deploy") || endpoint.includes("/api/dotfiles/deploy")) {
    const directiveInput = form.querySelector('[name="write_directive"]');
    const directive = directiveInput && typeof directiveInput.value === "string"
      ? directiveInput.value.trim()
      : "";
    if (!directive) {
      showToast("Backup & Sync deploy requires an explicit write directive.", true);
      setNetworkBanner("Backup & Sync deploy blocked until a write directive is provided.", true);
      return;
    }
  }
  const formData = buildFormData(form);
  if (endpoint.includes("/api/config-sync/") || endpoint.includes("/api/dotfiles/")) {
    const targetEnv = formData.get("target_env");
    if (targetEnv) {
      formData.set("target", String(targetEnv));
    }
    const directive = formData.get("write_directive");
    if (directive !== null) {
      formData.set("directive", String(directive));
    }
    if (endpoint.includes("/deploy")) {
      formData.set("apply", "true");
    }
  }
  setFormBusy(form, true);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const message = payloadErrorMessage(payload);
      showToast(message, true);
      setNetworkBanner(message, true);
      return;
    }
    if (payload.run_id) {
      showToast(`Run started: ${payload.run_id.slice(0, 10)}`);
      setPanelStatus("Running", true);
    } else if (payload.job_id) {
      showToast(`Payload job queued: ${payload.job_id.slice(0, 10)}`);
      setPanelStatus("Running", true);
      trackPayloadJob(payload.job_id);
    } else if (payload.service_id) {
      showToast(`Integration updated: ${payload.service_id}`);
    } else if (payload.note) {
      showToast("Resolution note stored");
    } else if (payload.profile_id && payload.actions) {
      showToast(
        `Dependency profile ${payload.profile_id}: ${payload.installed_count}/${payload.tool_count} ready`
      );
    } else if (endpoint.includes("/api/config-sync/") || endpoint.includes("/api/dotfiles/")) {
      const action = endpoint.split("/").pop() || "config-sync";
      showToast(`Backup & Sync ${action} complete`);
      renderDotfiles(payload.config_sync || payload.dotfiles || payload || {});
    } else {
      showToast("Action completed");
    }
    if (endpoint.includes("/api/config-sync/") || endpoint.includes("/api/dotfiles/")) {
      refreshDotfiles();
    }
    refreshDashboard();
  } catch (error) {
    const message = `Request failed: ${error}`;
    showToast(message, true);
    setNetworkBanner(message, true);
    setPanelStatus("Offline", false);
  } finally {
    setFormBusy(form, false);
  }
}

async function refreshDashboard() {
  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    if (!response.ok) {
      setPanelStatus("Offline", false);
      setLastRefresh("Stale");
      setNetworkBanner(`Dashboard API returned ${response.status}`, true);
      return;
    }
    const payload = await response.json();
    renderMetrics(payload.metrics || {});
    renderRuns(payload.runs || []);
    renderPayloads(payload.payloads || []);
    renderStandards(payload.standards_summary || {}, payload.standards || []);
    renderTooling(payload.tooling || { profiles: [], available_managers: [] });
    renderIntegrations(payload.integrations || { services: [] });
    renderLearning(payload.learning || { known_good: [], errors: [] });
    if (payload.config_sync || payload.dotfiles) {
      renderDotfiles(payload.config_sync || payload.dotfiles);
    }
    setNetworkBanner("");
    setPanelStatus("Connected", true);
    setLastRefresh(`Updated ${new Date().toLocaleTimeString()}`);
  } catch {
    setPanelStatus("Offline", false);
    setLastRefresh("Stale");
    setNetworkBanner("Dashboard refresh failed. Check the backend logs.", true);
  }
}

document.querySelectorAll("form[data-endpoint]").forEach((form) => {
  form.addEventListener("submit", submitActionForm);
});

refreshDashboard();
refreshDotfiles();
setInterval(refreshDashboard, 12000);
setInterval(refreshDotfiles, 20000);

window.addEventListener("offline", () => {
  setPanelStatus("Offline", false);
  setNetworkBanner("Browser reports offline state.", true);
});

window.addEventListener("online", () => {
  setPanelStatus("Connected", true);
  setNetworkBanner("");
  refreshDashboard();
});
