/**
 * EvoNexus CLI — plugin subcommand
 *
 * Usage:
 *   npx @evoapi/evo-nexus plugin install <url>
 *   npx @evoapi/evo-nexus plugin list
 *   npx @evoapi/evo-nexus plugin uninstall <slug>
 *   npx @evoapi/evo-nexus plugin update <slug>
 *   npx @evoapi/evo-nexus plugin init <slug> [--name "Display Name"]
 *   npx @evoapi/evo-nexus plugin dev [--host-url <url>]
 *   npx @evoapi/evo-nexus plugin validate [path]
 *   npx @evoapi/evo-nexus plugin pack [path]
 */

import { execSync, spawn } from "child_process";
import {
  existsSync,
  mkdirSync,
  writeFileSync,
  readdirSync,
  readFileSync,
  createReadStream,
} from "fs";
import { resolve, join, basename, dirname } from "path";
import { fileURLToPath } from "url";
import * as crypto from "crypto";
import * as readline from "readline";

const GREEN  = "\x1b[92m";
const CYAN   = "\x1b[96m";
const YELLOW = "\x1b[93m";
const RED    = "\x1b[91m";
const BOLD   = "\x1b[1m";
const DIM    = "\x1b[2m";
const RESET  = "\x1b[0m";

const __dir      = dirname(fileURLToPath(import.meta.url));
const SKELETON   = resolve(__dir, "../../templates/plugin-skeleton");

// Slug pattern mirrors the server's _SLUG_RE in plugin_schema.py:
// ^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$  (3-64 chars, no leading/trailing hyphen)
const SLUG_RE    = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

// ── API helpers ───────────────────────────────────────────────────────────────

function apiBase() {
  return process.env.EVONEXUS_API_URL ?? "http://localhost:8080";
}

async function apiRequest(method, path, body) {
  const token = process.env.DASHBOARD_API_TOKEN ?? "";
  const url   = `${apiBase()}/api${path}`;
  const opts  = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  };
  const { default: fetch } = await import("node-fetch").catch(() => ({
    default: globalThis.fetch,
  }));
  const fn  = fetch ?? globalThis.fetch;
  const res = await fn(url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${method} ${path} -> ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Existing subcommands (install / list / uninstall / update) ────────────────

async function cmdInstall(args) {
  const url = args[0];
  if (!url) {
    console.error(`  ${RED}Usage: plugin install <https-url>${RESET}\n`);
    process.exit(1);
  }
  console.log(`  ${BOLD}Installing plugin from:${RESET} ${DIM}${url}${RESET}\n`);
  try {
    const data = await apiRequest("POST", "/plugins/install", { source_url: url });
    console.log(`  ${GREEN}ok${RESET} Installed: ${BOLD}${data.slug}${RESET} (status: ${data.status})`);
    if (data.warnings && data.warnings.length > 0) {
      console.log(`\n  ${YELLOW}Warnings:${RESET}`);
      data.warnings.forEach((w) => console.log(`    ${YELLOW}!${RESET} ${w}`));
    }
    if (data.routine_activation_pending) {
      console.log(`\n  ${YELLOW}!${RESET} Restart the dashboard to activate plugin routines.`);
    }
    console.log();
  } catch (e) {
    console.error(`  ${RED}Install failed: ${e.message}${RESET}\n`);
    process.exit(1);
  }
}

async function cmdList() {
  try {
    const plugins = await apiRequest("GET", "/plugins");
    if (!Array.isArray(plugins) || plugins.length === 0) {
      console.log(`  ${DIM}No plugins installed.${RESET}\n`);
      return;
    }
    console.log(`\n  ${BOLD}Installed plugins (${plugins.length}):${RESET}\n`);
    const maxSlug = Math.max(...plugins.map((p) => p.slug.length), 4);
    const maxVer  = Math.max(...plugins.map((p) => p.version.length), 7);
    console.log(`  ${"SLUG".padEnd(maxSlug)}  ${"VERSION".padEnd(maxVer)}  STATUS`);
    console.log(`  ${"-".repeat(maxSlug + maxVer + 12)}`);
    for (const p of plugins) {
      const status =
        p.status === "active"  ? `${GREEN}active${RESET}` :
        p.status === "broken"  ? `${RED}broken${RESET}`   :
        `${YELLOW}${p.status}${RESET}`;
      const enabled = p.enabled ? "" : ` ${DIM}[disabled]${RESET}`;
      console.log(
        `  ${p.slug.padEnd(maxSlug)}  ${p.version.padEnd(maxVer)}  ${status}${enabled}`
      );
    }
    console.log();
  } catch (e) {
    console.error(`  ${RED}List failed: ${e.message}${RESET}\n`);
    process.exit(1);
  }
}

async function cmdUninstall(args) {
  const slug = args[0];
  if (!slug) {
    console.error(`  ${RED}Usage: plugin uninstall <slug>${RESET}\n`);
    process.exit(1);
  }
  console.log(`  ${BOLD}Uninstalling:${RESET} ${slug}\n`);
  try {
    await apiRequest("DELETE", `/plugins/${slug}`);
    console.log(`  ${GREEN}ok${RESET} Uninstalled: ${slug}\n`);
  } catch (e) {
    console.error(`  ${RED}Uninstall failed: ${e.message}${RESET}\n`);
    process.exit(1);
  }
}

async function cmdUpdate(args) {
  const slug = args[0];
  if (!slug) {
    console.error(`  ${RED}Usage: plugin update <slug>${RESET}\n`);
    process.exit(1);
  }
  console.log(`  ${BOLD}Updating:${RESET} ${slug}\n`);
  try {
    const result = await apiRequest("POST", `/plugins/${slug}/update`, {});
    console.log(
      `  ${GREEN}ok${RESET} Updated ${BOLD}${slug}${RESET}: ${result.from_version} -> ${result.to_version}\n`
    );
  } catch (e) {
    console.error(`  ${RED}Update failed: ${e.message}${RESET}\n`);
    process.exit(1);
  }
}

// ── v2 commands ───────────────────────────────────────────────────────────────

/**
 * plugin init <slug> [--name "Display Name"]
 *
 * Scaffolds a v2 TypeScript workspace project from the plugin skeleton.
 * Slug is validated against the server's pattern.
 * Display name is taken from --name flag or prompted interactively.
 */
async function cmdInit(args) {
  // Parse --name flag
  let nameFlag = null;
  const filteredArgs = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--name" && args[i + 1]) {
      nameFlag = args[i + 1];
      i++;
    } else {
      filteredArgs.push(args[i]);
    }
  }

  const rawSlug = filteredArgs[0];
  if (!rawSlug) {
    console.error(`  ${RED}Usage: plugin init <slug> [--name "Display Name"]${RESET}\n`);
    console.error(`  ${DIM}slug must match ^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$${RESET}\n`);
    process.exit(1);
  }

  const slug = rawSlug.toLowerCase().trim();
  if (!SLUG_RE.test(slug)) {
    console.error(
      `  ${RED}Invalid slug: "${slug}"${RESET}\n` +
      `  ${DIM}Must match ^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$ (3-64 chars, kebab-case)${RESET}\n`
    );
    process.exit(1);
  }

  // Prompt for display name if not given via flag
  let displayName = nameFlag;
  if (!displayName) {
    displayName = await promptLine(`  Plugin display name [${slug}]: `);
    if (!displayName.trim()) displayName = slug;
  }

  const targetDir  = resolve(process.cwd(), slug);
  const slugUnder  = slug.replace(/-/g, "_"); // table prefix: my-plugin -> my_plugin

  if (existsSync(targetDir)) {
    console.error(`  ${RED}Directory '${slug}' already exists.${RESET}\n`);
    process.exit(1);
  }

  if (!existsSync(SKELETON)) {
    console.error(`  ${RED}Skeleton not found at: ${SKELETON}${RESET}\n`);
    process.exit(1);
  }

  // Copy skeleton, replacing placeholders
  copyDir(SKELETON, targetDir, slug, displayName, slugUnder);

  console.log(`
  ${GREEN}ok${RESET} Plugin scaffold created: ${BOLD}${slug}/${RESET}

  ${BOLD}Next steps:${RESET}
  ${CYAN}1.${RESET} cd ${slug}/
  ${CYAN}2.${RESET} npm install
  ${CYAN}3.${RESET} npm run build        # verify it compiles
  ${CYAN}4.${RESET} npx @evoapi/evo-nexus plugin validate .
  ${CYAN}5.${RESET} npx @evoapi/evo-nexus plugin dev      # watch + reload

  ${DIM}Tip: edit plugin.yaml to declare your capabilities, then implement${RESET}
  ${DIM}     src/pages/ and src/widgets/ using @evonexus/ui primitives.${RESET}
`);
}

function copyDir(src, dest, slug, displayName, slugUnder) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src, { withFileTypes: true })) {
    if (entry.name === ".git") continue;
    const srcPath  = join(src, entry.name);
    const destName = entry.name.replace(/__SLUG__/g, slug);
    const destPath = join(dest, destName);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath, slug, displayName, slugUnder);
    } else {
      let content = readFileSync(srcPath, "utf-8");
      content = content
        .replace(/__SLUG_UNDER__/g, slugUnder)
        .replace(/__SLUG__/g, slug)
        .replace(/__NAME__/g, displayName);
      writeFileSync(destPath, content);
    }
  }
}

function promptLine(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

/**
 * plugin dev [--host-url <url>]
 *
 * Runs vite build --watch in the current plugin directory.
 * After each rebuild, optionally notifies the host via POST /api/plugins/reload
 * (host-side support for this endpoint is provided by Step 2 / host renderer).
 *
 * Notification contract (for Step 2 to implement):
 *   POST {hostUrl}/api/plugins/reload  { "slug": "<slug>" }
 *   Response: 200 OK (host hot-reloads the plugin route)
 *
 * If the host endpoint is not available, dev mode still works — you get
 * file-watched builds. Refresh the browser manually.
 */
async function cmdDev(args) {
  // Parse --host-url flag
  let hostUrl = process.env.EVONEXUS_API_URL ?? null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--host-url" && args[i + 1]) {
      hostUrl = args[i + 1];
    }
  }

  const pluginDir = process.cwd();
  const manifest  = loadManifestOrNull(pluginDir);
  const slug      = manifest?.id ?? null;

  if (!existsSync(join(pluginDir, "vite.config.ts")) &&
      !existsSync(join(pluginDir, "vite.config.js"))) {
    console.error(
      `  ${RED}No vite.config.ts found in current directory.${RESET}\n` +
      `  ${DIM}Run this command from your plugin root.${RESET}\n`
    );
    process.exit(1);
  }

  console.log(`  ${BOLD}Starting plugin dev watcher...${RESET}`);
  if (hostUrl && slug) {
    console.log(`  ${DIM}Host reload: POST ${hostUrl}/api/plugins/reload after each build${RESET}`);
  } else {
    console.log(`  ${YELLOW}!${RESET} No host URL set — rebuild completes, refresh browser manually.`);
    console.log(`  ${DIM}Set EVONEXUS_API_URL or pass --host-url <url> to enable auto-reload.${RESET}`);
  }
  console.log();

  // Run vite build --watch
  const viteBin = resolveLocalBin(pluginDir, "vite");
  const child   = spawn(viteBin, ["build", "--watch"], {
    cwd:   pluginDir,
    stdio: ["inherit", "pipe", "pipe"],
  });

  let buildBuffer = "";

  child.stdout.on("data", (chunk) => {
    const text = chunk.toString();
    process.stdout.write(text);
    buildBuffer += text;
    if (buildBuffer.includes("built in") || buildBuffer.includes("watching for file changes")) {
      if (buildBuffer.includes("built in") && hostUrl && slug) {
        notifyHostReload(hostUrl, slug);
      }
      buildBuffer = "";
    }
  });

  child.stderr.on("data", (chunk) => {
    process.stderr.write(chunk);
  });

  child.on("exit", (code) => {
    if (code !== 0) {
      console.error(`\n  ${RED}Vite exited with code ${code}${RESET}\n`);
      process.exit(code ?? 1);
    }
  });

  // Keep alive until SIGINT
  process.on("SIGINT", () => {
    child.kill("SIGINT");
    process.exit(0);
  });

  // Never resolves — watch mode runs until user stops it
  await new Promise(() => {});
}

function resolveLocalBin(cwd, name) {
  const local = join(cwd, "node_modules", ".bin", name);
  return existsSync(local) ? local : name;
}

async function notifyHostReload(hostUrl, slug) {
  try {
    const token = process.env.DASHBOARD_API_TOKEN ?? "";
    const { default: fetch } = await import("node-fetch").catch(() => ({
      default: globalThis.fetch,
    }));
    const fn = fetch ?? globalThis.fetch;
    await fn(`${hostUrl}/api/plugins/reload`, {
      method:  "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ slug }),
    });
  } catch {
    // Non-fatal — host endpoint may not be available yet (Step 2 pending)
  }
}

/**
 * plugin validate [path]
 *
 * Offline validation of a plugin manifest — fail-fast before pushing to the host.
 *
 * Checks performed (mirrors the server-side gate in plugin_schema.py):
 *   1. schema_version is "2.0" (rejects v0 / v1.0 with clear message)
 *   2. id matches slug pattern ^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$
 *   3. Required fields present (id, name, version, description, author, license)
 *   4. No legacy install.sql (v1.0 / v0 artefact)
 *   5. If sql_migrations in capabilities: both install.sqlite.sql AND install.postgres.sql exist
 *   6. Capability declarations match blocks present (e.g. ui_pages declared -> ui_pages block exists)
 *   7. readonly_data / writable_data table names start with {slug}_ prefix
 *   8. writable_data[].json_schema are valid JSON Schemas (structural check)
 *
 * Exits 0 on success, 1 on failure.
 */
async function cmdValidate(args) {
  const pluginPath = resolve(process.cwd(), args[0] ?? ".");
  const yamlPath   = join(pluginPath, "plugin.yaml");

  if (!existsSync(yamlPath)) {
    console.error(`  ${RED}plugin.yaml not found at: ${yamlPath}${RESET}\n`);
    process.exit(1);
  }

  let yaml;
  try {
    yaml = await loadYaml(readFileSync(yamlPath, "utf-8"));
  } catch (e) {
    console.error(`  ${RED}Failed to parse plugin.yaml: ${e.message}${RESET}\n`);
    process.exit(1);
  }

  const errors   = [];
  const warnings = [];

  // ── 1. schema_version gate ────────────────────────────────────────────────
  const schemaVersion = yaml.schema_version;
  if (!schemaVersion) {
    errors.push(
      "plugin.yaml: missing schema_version. " +
      "v2 plugins must declare schema_version: \"2.0\""
    );
  } else if (schemaVersion === "1.0" || schemaVersion === "1.0.0") {
    errors.push(
      `plugin.yaml: schema_version "${schemaVersion}" is not supported. ` +
      "Migrate to schema 2.0 (React + @evonexus/ui) — see docs/plugin-contract.md"
    );
  } else if (schemaVersion !== "2.0") {
    errors.push(
      `plugin.yaml: unknown schema_version "${schemaVersion}". ` +
      "This CLI supports schema_version: \"2.0\" only."
    );
  }

  // ── 2. Slug pattern ───────────────────────────────────────────────────────
  const slug = yaml.id;
  if (!slug) {
    errors.push("plugin.yaml: id is required");
  } else if (!SLUG_RE.test(slug)) {
    errors.push(
      `plugin.yaml: id "${slug}" does not match pattern ` +
      "^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$ (3-64 chars, kebab-case)"
    );
  }

  // ── 3. Required fields ────────────────────────────────────────────────────
  for (const field of ["name", "version", "description", "author", "license"]) {
    if (!yaml[field]) errors.push(`plugin.yaml: required field "${field}" is missing`);
  }

  // ── 4. Legacy install.sql ─────────────────────────────────────────────────
  if (existsSync(join(pluginPath, "migrations", "install.sql"))) {
    errors.push(
      "migrations/install.sql: legacy file not allowed in v2. " +
      "Use install.sqlite.sql and install.postgres.sql instead (dialect-aware, required since contract v1.0.0)."
    );
  }

  // ── 5. Dialect-aware SQL (if sql_migrations declared) ────────────────────
  const capabilities = Array.isArray(yaml.capabilities) ? yaml.capabilities : [];
  if (capabilities.includes("sql_migrations")) {
    const migrationsDir = join(pluginPath, "migrations");
    const required = [
      "install.sqlite.sql",
      "install.postgres.sql",
      "uninstall.sqlite.sql",
      "uninstall.postgres.sql",
    ];
    for (const f of required) {
      if (!existsSync(join(migrationsDir, f))) {
        errors.push(
          `migrations/${f}: file required when sql_migrations is declared in capabilities.`
        );
      }
    }
  }

  // ── 6. Capability ↔ block presence ────────────────────────────────────────
  const capabilityBlocks = {
    ui_pages:      "ui_pages",
    widgets:       "widgets",
    readonly_data: "readonly_data",
    writable_data: "writable_data",
    public_pages:  "public_pages",
    safe_uninstall:"safe_uninstall",
    claude_hooks:  "claude_hooks",
  };
  for (const [cap, block] of Object.entries(capabilityBlocks)) {
    const declared = capabilities.includes(cap);
    const present  = yaml[block] != null && (
      !Array.isArray(yaml[block]) || yaml[block].length > 0
    );
    if (declared && !present) {
      warnings.push(
        `plugin.yaml: capability "${cap}" is declared but no "${block}" block is present.`
      );
    }
    if (!declared && present) {
      warnings.push(
        `plugin.yaml: "${block}" block is present but "${cap}" is not listed in capabilities.`
      );
    }
  }

  // ── 7. Table name prefix ──────────────────────────────────────────────────
  if (slug) {
    const slugUnder = slug.replace(/-/g, "_");
    const prefix    = `${slugUnder}_`;

    for (const resource of yaml.readonly_data ?? []) {
      const sql = resource.sql ?? "";
      // Basic check: look for FROM clauses referencing un-prefixed tables
      const tableMatches = sql.match(/\bFROM\s+([a-z_][a-z0-9_]*)/gi) ?? [];
      for (const m of tableMatches) {
        const table = m.replace(/^FROM\s+/i, "");
        if (!table.startsWith(prefix) && !table.startsWith("_")) {
          warnings.push(
            `readonly_data[${resource.id}]: SQL references table "${table}" ` +
            `which does not start with "${prefix}" prefix.`
          );
        }
      }
    }

    for (const resource of yaml.writable_data ?? []) {
      if (resource.table && !resource.table.startsWith(prefix)) {
        errors.push(
          `writable_data[${resource.id}]: table "${resource.table}" must start with "${prefix}".`
        );
      }
    }
  }

  // ── 8. JSON Schema validity for writable_data ────────────────────────────
  for (const resource of yaml.writable_data ?? []) {
    if (!resource.json_schema) {
      warnings.push(
        `writable_data[${resource.id}]: no json_schema declared — ` +
        "<SchemaForm> will have nothing to render."
      );
      continue;
    }
    const schemaErr = validateJsonSchema(resource.json_schema, resource.id);
    if (schemaErr) errors.push(schemaErr);
  }

  // ── Report ────────────────────────────────────────────────────────────────
  const hasFatal = errors.length > 0;
  console.log(`\n  ${BOLD}plugin validate${RESET} ${DIM}${pluginPath}${RESET}\n`);

  if (errors.length === 0 && warnings.length === 0) {
    console.log(`  ${GREEN}ok${RESET} All checks passed.\n`);
    return;
  }

  for (const e of errors) {
    console.log(`  ${RED}error${RESET}  ${e}`);
  }
  for (const w of warnings) {
    console.log(`  ${YELLOW}warn${RESET}   ${w}`);
  }
  console.log();

  if (hasFatal) {
    process.exit(1);
  }
}

/**
 * Basic structural check that a JSON Schema object is valid.
 * Only checks "type" is a recognized value and "properties" is an object.
 * Full validation is left to the server (Pydantic).
 */
function validateJsonSchema(schema, resourceId) {
  if (typeof schema !== "object" || schema === null) {
    return `writable_data[${resourceId}].json_schema: must be a JSON Schema object`;
  }
  const VALID_TYPES = new Set(["object", "array", "string", "number", "integer", "boolean", "null"]);
  if (schema.type && !VALID_TYPES.has(schema.type)) {
    return (
      `writable_data[${resourceId}].json_schema: invalid type "${schema.type}". ` +
      "Must be one of: object, array, string, number, integer, boolean, null"
    );
  }
  if (schema.properties !== undefined && typeof schema.properties !== "object") {
    return `writable_data[${resourceId}].json_schema: "properties" must be an object`;
  }
  return null;
}

/**
 * plugin pack [path]
 *
 * Builds the plugin (clean vite build), then creates a distribution tarball
 * containing: dist/ + plugin.yaml + migrations/ + README.md + LICENSE (if present).
 * Source files (src/, node_modules/, .git/) are never included.
 *
 * Outputs: <slug>-<version>.tgz  +  <slug>-<version>.tgz.sha256
 * Prints: tarball path and SHA256 on stdout.
 */
async function cmdPack(args) {
  const pluginPath = resolve(process.cwd(), args[0] ?? ".");
  const manifest   = loadManifestOrNull(pluginPath);

  if (!manifest) {
    console.error(
      `  ${RED}plugin.yaml not found at: ${join(pluginPath, "plugin.yaml")}${RESET}\n`
    );
    process.exit(1);
  }

  const { id: slug, version } = manifest;
  if (!slug || !version) {
    console.error(`  ${RED}plugin.yaml must declare id and version.${RESET}\n`);
    process.exit(1);
  }

  const distDir = join(pluginPath, "dist");

  // ── Build ──────────────────────────────────────────────────────────────────
  console.log(`\n  ${BOLD}Building plugin...${RESET}\n`);
  try {
    const viteBin = resolveLocalBin(pluginPath, "vite");
    execSync(`${viteBin} build`, { cwd: pluginPath, stdio: "inherit" });
  } catch (e) {
    console.error(`\n  ${RED}Build failed — fix errors before packing.${RESET}\n`);
    process.exit(1);
  }

  if (!existsSync(distDir)) {
    console.error(`  ${RED}dist/ not found after build — check vite.config.ts outDir.${RESET}\n`);
    process.exit(1);
  }

  // ── Collect tarball entries ────────────────────────────────────────────────
  const tarballName = `${slug}-${version}.tgz`;
  const tarballPath = join(pluginPath, tarballName);
  const sha256Path  = `${tarballPath}.sha256`;

  // Files/dirs to include (relative to pluginPath)
  const includes = ["dist", "plugin.yaml", "migrations", "README.md"];
  if (existsSync(join(pluginPath, "LICENSE")))   includes.push("LICENSE");
  if (existsSync(join(pluginPath, "LICENSE.md"))) includes.push("LICENSE.md");

  // Filter to items that actually exist
  const existing = includes.filter((p) => existsSync(join(pluginPath, p)));

  // ── Pack via tar ───────────────────────────────────────────────────────────
  console.log(`\n  ${BOLD}Packing ${tarballName}...${RESET}\n`);
  try {
    const entryList = existing.join(" ");
    execSync(`tar -czf "${tarballPath}" ${entryList}`, {
      cwd:   pluginPath,
      stdio: "inherit",
    });
  } catch (e) {
    console.error(`  ${RED}tar failed: ${e.message}${RESET}\n`);
    process.exit(1);
  }

  // ── SHA256 ─────────────────────────────────────────────────────────────────
  const sha256 = await sha256File(tarballPath);
  writeFileSync(sha256Path, `${sha256}  ${tarballName}\n`);

  console.log(`  ${GREEN}ok${RESET}  Tarball: ${BOLD}${tarballPath}${RESET}`);
  console.log(`  ${GREEN}ok${RESET}  SHA256:  ${BOLD}${sha256}${RESET}`);
  console.log(`         Written: ${DIM}${sha256Path}${RESET}\n`);

  // Machine-readable output on stdout (for scripting)
  console.log(tarballPath);
  console.log(sha256);
}

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash   = crypto.createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (d) => hash.update(d));
    stream.on("end",  () => resolve(hash.digest("hex")));
    stream.on("error", reject);
  });
}

// ── YAML loader (no external dep — minimal hand-rolled parser) ────────────────

/**
 * Parses the subset of YAML used in plugin.yaml:
 *   - Top-level key: value pairs (strings, numbers, arrays, nested objects)
 *   - Block sequences (- item)
 *   - Quoted and unquoted strings
 *   - Comments (#)
 *   - Nested maps (2-space indent)
 *
 * This is intentionally minimal — only what plugin.yaml uses.
 * Full YAML spec is not covered.
 */
async function loadYaml(text) {
  // Try js-yaml from node_modules if available (plugins that have it)
  try {
    const mod = await import("js-yaml");
    return mod.default ? mod.default.load(text) : mod.load(text);
  } catch {
    // js-yaml not available — use minimal parser
    return parseMinimalYaml(text);
  }
}

function parseMinimalYaml(text) {
  const lines = text.split("\n");
  const root  = {};
  const stack = [{ indent: -1, obj: root }];

  for (let i = 0; i < lines.length; i++) {
    const raw  = lines[i];
    const line = raw.replace(/#.*$/, "").trimEnd();
    if (!line.trim()) continue;

    const indent = line.length - line.trimStart().length;
    const trimmed = line.trim();

    // Pop stack to current indent
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }
    const current = stack[stack.length - 1].obj;

    if (trimmed.startsWith("- ")) {
      // Sequence item
      const val = parseYamlValue(trimmed.slice(2).trim());
      const parentKey = stack[stack.length - 1].key;
      if (Array.isArray(current[parentKey])) {
        current[parentKey].push(val);
      }
      continue;
    }

    const colonIdx = trimmed.indexOf(": ");
    if (colonIdx === -1 && trimmed.endsWith(":")) {
      // Key with nested map or sequence
      const key = trimmed.slice(0, -1).trim();
      // Peek ahead
      const nextLine = lines[i + 1] ?? "";
      if (nextLine.trim().startsWith("- ")) {
        current[key] = [];
        stack.push({ indent, obj: current[key], key });
      } else {
        current[key] = {};
        stack.push({ indent, obj: current[key], key });
      }
      continue;
    }

    if (colonIdx >= 0) {
      const key = trimmed.slice(0, colonIdx).trim();
      const val = parseYamlValue(trimmed.slice(colonIdx + 2).trim());
      if (Array.isArray(current)) {
        // Should not happen in plugin.yaml at top-level
      } else {
        current[key] = val;
        stack[stack.length - 1].key = key;
      }
      continue;
    }

    // Bare string in sequence
    if (Array.isArray(current)) {
      current.push(parseYamlValue(trimmed));
    }
  }

  return root;
}

function parseYamlValue(v) {
  if (!v || v === "~" || v === "null") return null;
  if (v === "true")  return true;
  if (v === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
  // Quoted string
  if ((v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))) {
    return v.slice(1, -1);
  }
  return v;
}

function loadManifestOrNull(pluginPath) {
  const yamlPath = join(pluginPath, "plugin.yaml");
  if (!existsSync(yamlPath)) return null;
  try {
    const text = readFileSync(yamlPath, "utf-8");
    // Synchronous parse — use minimal parser (no async needed here)
    return parseMinimalYaml(text);
  } catch {
    return null;
  }
}

// ── Help ──────────────────────────────────────────────────────────────────────

function showHelp() {
  console.log(`
  ${BOLD}EvoNexus Plugin CLI${RESET}

  ${BOLD}Usage:${RESET}
    npx @evoapi/evo-nexus plugin <subcommand> [args]

  ${BOLD}v2 plugin authoring:${RESET}
    ${CYAN}init <slug>${RESET}           Scaffold a new v2 plugin workspace (TypeScript + Vite)
    ${CYAN}dev${RESET}                   Watch-mode build + hot-reload notification to host
    ${CYAN}validate [path]${RESET}       Offline manifest validation (fails fast before install)
    ${CYAN}pack [path]${RESET}           Build + create distributable tarball with SHA256

  ${BOLD}Host management:${RESET}
    ${CYAN}install <url>${RESET}         Install a plugin from an HTTPS URL or local tarball
    ${CYAN}list${RESET}                  List installed plugins
    ${CYAN}uninstall <slug>${RESET}      Uninstall a plugin by slug
    ${CYAN}update <slug>${RESET}         Update a plugin (uninstall + reinstall from source)

  ${BOLD}Flags for init:${RESET}
    ${CYAN}--name${RESET} "Display Name" Plugin display name (skips interactive prompt)

  ${BOLD}Flags for dev:${RESET}
    ${CYAN}--host-url${RESET} <url>       Host to notify after each rebuild (default: EVONEXUS_API_URL)

  ${BOLD}Environment:${RESET}
    EVONEXUS_API_URL      Dashboard URL (default: http://localhost:8080)
    DASHBOARD_API_TOKEN   Bearer token for authenticated requests

  ${BOLD}Examples:${RESET}
    npx @evoapi/evo-nexus plugin init my-crm-plugin --name "My CRM Plugin"
    npx @evoapi/evo-nexus plugin validate .
    npx @evoapi/evo-nexus plugin pack
    npx @evoapi/evo-nexus plugin dev --host-url http://localhost:8080
    npx @evoapi/evo-nexus plugin install https://github.com/org/my-plugin
    npx @evoapi/evo-nexus plugin list
`);
}

// ── Entry point ───────────────────────────────────────────────────────────────

export async function runPlugin(args) {
  const sub  = args[0];
  const rest = args.slice(1);

  switch (sub) {
    case "install":   return cmdInstall(rest);
    case "list":      return cmdList();
    case "uninstall": return cmdUninstall(rest);
    case "update":    return cmdUpdate(rest);
    case "init":      return cmdInit(rest);
    case "dev":       return cmdDev(rest);
    case "validate":  return cmdValidate(rest);
    case "pack":      return cmdPack(rest);
    case "--help":
    case "-h":
    case undefined:
      showHelp();
      break;
    default:
      console.error(`  ${RED}Unknown plugin subcommand: ${sub}${RESET}`);
      showHelp();
      process.exit(1);
  }
}
