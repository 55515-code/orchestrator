import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { execFile } from "node:child_process";
import { promises as fsp, existsSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const PLUGIN_ID = "proton-bridge";

const DEFAULT_ENV_FILE = path.join(os.homedir(), ".config", "substrate", "proton-bridge-hook.env");
const DEFAULT_HOOK_SERVICE = "proton-bridge-hook.service";
const SYSTEMCTL_BIN = process.env.OPENCLAW_SYSTEMCTL || "systemctl";

const MANAGED_KEY = {
  email: "PROTON_EMAIL",
  bridgePassword: "PROTON_BRIDGE_PW",
  imapHost: "PROTON_IMAP_HOST",
  imapPort: "PROTON_IMAP_PORT",
  pollSeconds: "PROTON_POLL_SECONDS",
  hookUrl: "OPENCLAW_HOOK_URL",
  hookToken: "OPENCLAW_HOOK_TOKEN",
};

const SECRET_FIELDS = new Set(["bridgePassword", "hookToken"]);

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function resolveEntryConfig(configSnapshot) {
  const entry = configSnapshot?.plugins?.entries?.[PLUGIN_ID];
  return isRecord(entry) && isRecord(entry.config) ? entry.config : {};
}

function pickManagedFields(raw) {
  const out = {};
  for (const field of Object.keys(MANAGED_KEY)) {
    if (Object.prototype.hasOwnProperty.call(raw, field)) out[field] = raw[field];
  }
  return out;
}

function readOperational(raw) {
  const envFilePath =
    typeof raw.envFilePath === "string" && raw.envFilePath.trim() !== ""
      ? expandHome(raw.envFilePath.trim())
      : DEFAULT_ENV_FILE;
  const hookServiceName =
    typeof raw.hookServiceName === "string" && raw.hookServiceName.trim() !== ""
      ? raw.hookServiceName.trim()
      : DEFAULT_HOOK_SERVICE;
  return { envFilePath, hookServiceName };
}

function expandHome(p) {
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

function quoteEnvValue(value) {
  if (/^[A-Za-z0-9_.,:/@%+\-]+$/.test(value)) return value;
  return `"${value.replace(/(["\\$`])/gu, "\\$1")}"`;
}

function envKeyOfLine(line) {
  const match = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
  return match ? match[1] : null;
}

function serializeEnv(existingText, settings) {
  const controlled = new Map();
  for (const field of Object.keys(MANAGED_KEY)) {
    if (!Object.prototype.hasOwnProperty.call(settings, field)) continue;
    const raw = settings[field];
    if (raw === undefined || raw === null) continue;
    const envKey = MANAGED_KEY[field];
    const value = typeof raw === "string" ? raw : String(raw);
    if (value.includes("\n") || value.includes("\r")) {
      throw new Error(`${envKey} must not contain newlines`);
    }
    controlled.set(envKey, value === "" ? null : value);
  }

  const lines = existingText ? existingText.split(/\r?\n/) : [];
  const out = [];
  const present = new Set();

  for (const line of lines) {
    const key = envKeyOfLine(line);
    if (key && controlled.has(key)) {
      present.add(key);
      const wanted = controlled.get(key);
      if (wanted !== null) out.push(`${key}=${quoteEnvValue(wanted)}`);
      continue;
    }
    out.push(line);
  }

  for (const [key, value] of controlled) {
    if (value !== null && !present.has(key)) out.push(`${key}=${quoteEnvValue(value)}`);
  }

  while (out.length > 0 && out[out.length - 1] === "") out.pop();
  return out.join("\n") + (out.length > 0 ? "\n" : "");
}

async function readEnvText(envFilePath) {
  try {
    return await fsp.readFile(envFilePath, "utf8");
  } catch (err) {
    if (err && err.code === "ENOENT") return "";
    throw err;
  }
}

async function writeEnvFile(envFilePath, text) {
  await fsp.mkdir(path.dirname(envFilePath), { recursive: true });
  const tmp = `${envFilePath}.tmp-${process.pid}-${Date.now()}`;
  await fsp.writeFile(tmp, text, { encoding: "utf8", mode: 0o600 });
  await fsp.chmod(tmp, 0o600);
  await fsp.rename(tmp, envFilePath);
  await fsp.chmod(envFilePath, 0o600);
}

function systemctlEnv() {
  const env = { ...process.env };
  const uid = typeof process.getuid === "function" ? process.getuid() : undefined;
  if (!env.XDG_RUNTIME_DIR && uid !== undefined && existsSync(`/run/user/${uid}`)) {
    env.XDG_RUNTIME_DIR = `/run/user/${uid}`;
  }
  return env;
}

function runSystemctl(args, { timeoutMs = 30000 } = {}) {
  return new Promise((resolve, reject) => {
    execFile(
      SYSTEMCTL_BIN,
      ["--user", ...args],
      { env: systemctlEnv(), timeout: timeoutMs },
      (err, stdout, stderr) => {
        if (err) {
          const detail = `${stderr || err.message || ""}`.trim();
          reject(new Error(detail || `systemctl ${args.join(" ")} failed`));
          return;
        }
        resolve(`${stdout || ""}`.trim());
      },
    );
  });
}

async function getServiceState(hookServiceName) {
  try {
    return await runSystemctl(["is-active", hookServiceName], { timeoutMs: 10000 });
  } catch {
    return "unknown";
  }
}

async function reconcile({
  settings,
  envFilePath,
  hookServiceName,
  restart = true,
  dryRun = false,
  clearManaged = false,
}) {
  const existingText = await readEnvText(envFilePath);
  const nextText = clearManaged
    ? serializeEnv(existingText, Object.fromEntries(Object.keys(MANAGED_KEY).map((f) => [f, ""])))
    : serializeEnv(existingText, settings);
  const changed = nextText !== existingText;
  const result = {
    envFilePath,
    hookServiceName,
    dryRun,
    clearManaged,
    changed,
    wrote: false,
    restarted: false,
    serviceState: null,
    error: null,
  };
  if (dryRun) {
    result.serviceState = await getServiceState(hookServiceName);
    return result;
  }
  try {
    if (changed) {
      await writeEnvFile(envFilePath, nextText);
      result.wrote = true;
    }
    if (restart && changed) {
      await runSystemctl(["restart", hookServiceName]);
      result.restarted = true;
    }
  } catch (err) {
    result.error = err && err.message ? err.message : String(err);
    return result;
  }
  result.serviceState = await getServiceState(hookServiceName);
  return result;
}

function fieldLabel(field) {
  return field in MANAGED_KEY ? MANAGED_KEY[field] : field;
}

function displayValue(field, value) {
  if (value === undefined || value === null || value === "") return "(unset)";
  if (SECRET_FIELDS.has(field)) return "•••••• (set)";
  return String(value);
}

function mapEnvTextToFields(envText) {
  const byEnvKey = {};
  for (const line of envText.split(/\r?\n/)) {
    const key = envKeyOfLine(line);
    if (!key) continue;
    const eq = line.indexOf("=");
    byEnvKey[key] = line.slice(eq + 1).replace(/^"(.*)"$/u, "$1");
  }
  const out = {};
  for (const [field, envKey] of Object.entries(MANAGED_KEY)) {
    out[field] = byEnvKey[envKey];
  }
  return out;
}

async function buildStatus(configSnapshot) {
  const raw = resolveEntryConfig(configSnapshot);
  const op = readOperational(raw);
  const envText = await readEnvText(op.envFilePath);
  const envFields = mapEnvTextToFields(envText);
  const serviceState = await getServiceState(op.hookServiceName);
  const lineFor = (field, value, source) =>
    `  ${String(field).padEnd(16)} ${displayValue(field, value).padEnd(24)} (${source})`;
  const lines = [
    `Proton Mail Bridge settings`,
    `Env file : ${op.envFilePath}`,
    `Service  : ${op.hookServiceName} (${serviceState})`,
    ``,
    `Field             Value                    Source`,
  ];
  for (const field of Object.keys(MANAGED_KEY)) {
    const desired = raw[field];
    const effective = envFields[field];
    if (desired !== undefined && desired !== null && desired !== "") {
      lines.push(lineFor(field, desired, "openclaw config"));
    } else if (effective !== undefined && effective !== "") {
      lines.push(lineFor(field, effective, "env file"));
    } else {
      lines.push(`  ${field.padEnd(16)} ${`(unset)`.padEnd(24)} (script default / keyring)`);
    }
  }
  return { text: lines.join("\n"), op, serviceState, envFields, configFields: raw };
}

function formatReconcileResult(result) {
  const lines = [
    `Env file : ${result.envFilePath}`,
    `Service  : ${result.hookServiceName} (${result.serviceState})`,
    result.dryRun
      ? `Dry run  : ${result.changed ? "env file WOULD change" : "env file already matches config"}`
      : `Applied  : ${result.changed ? "env file updated" : "env file already matches config"}`,
  ];
  if (!result.dryRun) {
    if (result.wrote) lines.push(`Wrote    : mode-600 env file (atomic replace)`);
    if (result.restarted) lines.push(`Restarted: ${result.hookServiceName}`);
  }
  if (result.error) {
    lines.push(`Error    : ${result.error}`);
    lines.push(`Hint     : the env file may be written while the service restart failed; run "openclaw proton-bridge status"`);
  }
  return lines.join("\n");
}

function registerCli(api) {
  api.registerCli(
    ({ program, config }) => {
      const root = program
        .command("proton-bridge")
        .description("Manage the Proton Mail Bridge -> OpenClaw hook bridge integration");

      root
        .command("status")
        .description("Show desired vs effective bridge settings and hook service state")
        .action(async () => {
          try {
            const info = await buildStatus(config);
            console.log(info.text);
          } catch (err) {
            console.error(`proton-bridge: ${err && err.message ? err.message : err}`);
            process.exitCode = 1;
          }
        });

      root
        .command("apply")
        .description("Write plugin config to the env file and restart the hook service")
        .option("--dry-run", "show what would change without writing or restarting")
        .option("--no-restart", "write the env file but do not restart the hook service")
        .action(async (opts) => {
          try {
            const raw = resolveEntryConfig(config);
            const op = readOperational(raw);
            const result = await reconcile({
              settings: pickManagedFields(raw),
              envFilePath: op.envFilePath,
              hookServiceName: op.hookServiceName,
              restart: opts.restart !== false,
              dryRun: opts.dryRun === true,
            });
            console.log(formatReconcileResult(result));
            if (result.error) process.exitCode = 1;
          } catch (err) {
            console.error(`proton-bridge apply: ${err && err.message ? err.message : err}`);
            process.exitCode = 1;
          }
        });

      root
        .command("clear")
        .description("Remove all plugin-managed keys from the env file and restart the hook service")
        .option("--dry-run", "show what would change without writing or restarting")
        .option("--no-restart", "remove env keys but do not restart the hook service")
        .action(async (opts) => {
          try {
            const raw = resolveEntryConfig(config);
            const op = readOperational(raw);
            const result = await reconcile({
              settings: {},
              envFilePath: op.envFilePath,
              hookServiceName: op.hookServiceName,
              restart: opts.restart !== false,
              dryRun: opts.dryRun === true,
              clearManaged: true,
            });
            console.log(formatReconcileResult(result));
            console.log(`Note     : the hook falls back to its script defaults / secret-tool keyring for removed keys.`);
            console.log(`Note     : clear the "proton-bridge" section in the OpenClaw config (Settings) as well if it should be emptied.`);
            if (result.error) process.exitCode = 1;
          } catch (err) {
            console.error(`proton-bridge clear: ${err && err.message ? err.message : err}`);
            process.exitCode = 1;
          }
        });
    },
    {
      descriptors: [
        {
          name: "proton-bridge",
          description: "Manage the Proton Mail Bridge -> OpenClaw hook bridge integration",
          hasSubcommands: true,
        },
      ],
    },
  );
}

export default definePluginEntry({
  id: PLUGIN_ID,
  name: "Proton Mail Bridge",
  description: "Manages the Proton Mail Bridge -> OpenClaw hook bridge settings and systemd user service.",
  register(api) {
    const isFull = api.registrationMode === "full" || api.registrationMode === undefined;

    registerCli(api);

    if (!isFull) return;

    api.registerGatewayMethod(
      "protonBridge.status",
      async ({ params, respond }) => {
        try {
          const status = await buildStatus(api.config);
          respond(true, {
            envFilePath: status.op.envFilePath,
            hookServiceName: status.op.hookServiceName,
            serviceState: status.serviceState,
            fields: Object.fromEntries(
              Object.keys(MANAGED_KEY).map((field) => [
                field,
                {
                  configValue: displayValue(field, status.configFields[field]),
                  effectiveValue: displayValue(field, status.envFields[field]),
                },
              ]),
            ),
          });
        } catch (err) {
          respond(false, { error: err && err.message ? err.message : String(err) });
        }
      },
      { scope: "operator.read" },
    );

    api.registerGatewayMethod(
      "protonBridge.apply",
      async ({ params, respond }) => {
        try {
          const raw = resolveEntryConfig(api.config);
          const op = readOperational(raw);
          const result = await reconcile({
            settings: pickManagedFields(raw),
            envFilePath: op.envFilePath,
            hookServiceName: op.hookServiceName,
            restart: params?.restart !== false,
            dryRun: params?.dryRun === true,
          });
          respond(true, result);
        } catch (err) {
          respond(false, { error: err && err.message ? err.message : String(err) });
        }
      },
      { scope: "operator.write" },
    );

    api.registerService({
      id: "proton-bridge",
      start: async (ctx) => {
        const raw = resolveEntryConfig(ctx.config);
        const op = readOperational(raw);
        try {
          const result = await reconcile({
            settings: pickManagedFields(raw),
            envFilePath: op.envFilePath,
            hookServiceName: op.hookServiceName,
          });
          if (result.error) {
            ctx.logger.warn(`proton-bridge reconcile: ${result.error}`);
          } else if (result.wrote || result.restarted) {
            ctx.logger.info(
              `proton-bridge reconcile: env file ${result.wrote ? "updated" : "unchanged"}, service ${result.restarted ? "restarted" : "not restarted"} (state: ${result.serviceState})`,
            );
          }
        } catch (err) {
          ctx.logger.warn(`proton-bridge reconcile failed: ${err && err.message ? err.message : err}`);
        }
      },
      stop: async () => {},
    });
  },
});
