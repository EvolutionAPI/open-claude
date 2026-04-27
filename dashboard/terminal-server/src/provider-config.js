const fs = require('fs');
const path = require('path');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..', '..');
const PROVIDERS_PATH = path.join(WORKSPACE_ROOT, 'config', 'providers.json');
const CODEX_AUTH_FILE = path.join(WORKSPACE_ROOT, 'config', 'codex-auth.json');

const ALLOWED_CLI = new Set(['claude', 'openclaude']);
const ALLOWED_ENV_VARS = new Set([
  'ANTHROPIC_API_KEY',
  'CLAUDE_CODE_USE_OPENAI',
  'CLAUDE_CODE_USE_GEMINI',
  'CLAUDE_CODE_USE_BEDROCK',
  'CLAUDE_CODE_USE_VERTEX',
  'OPENAI_BASE_URL',
  'OPENAI_API_KEY',
  'OPENAI_MODEL',
  'CODEX_AUTH_JSON_PATH',
  'CODEX_API_KEY',
  'GEMINI_API_KEY',
  'GEMINI_MODEL',
  'AWS_REGION',
  'AWS_BEARER_TOKEN_BEDROCK',
  'ANTHROPIC_VERTEX_PROJECT_ID',
  'CLOUD_ML_REGION',
]);

// ---- TKR Customization: Failover routing support ----
const DEFAULT_FAILOVER_ORDER = [
  'anthropic',
  'openrouter',
  'openai',
  'codex_auth',
  'gemini',
  'bedrock',
  'vertex',
];

function _normalizeModel(model) {
  return (model || '').trim().toLowerCase();
}

function loadProvidersFile() {
  try {
    if (!fs.existsSync(PROVIDERS_PATH)) {
      return { active_provider: 'anthropic', providers: {} };
    }
    return JSON.parse(fs.readFileSync(PROVIDERS_PATH, 'utf8'));
  } catch {
    return { active_provider: 'anthropic', providers: {} };
  }
}

function getProviderRouting(config, activeProviderId = null) {
  const providers = config?.providers || {};
  const active = activeProviderId || config?.active_provider || 'anthropic';
  const routing = config?.routing && typeof config.routing === 'object' ? config.routing : {};
  const seen = new Set();
  const ordered = [];

  const append = (providerId) => {
    if (!providerId || seen.has(providerId)) return;
    const provider = providers[providerId];
    if (!provider || provider.coming_soon) return;
    seen.add(providerId);
    ordered.push(providerId);
  };

  append(active);
  if (routing.enabled !== false && Array.isArray(routing.failover_order)) {
    routing.failover_order.forEach(append);
  }
  DEFAULT_FAILOVER_ORDER.forEach(append);
  Object.keys(providers).forEach(append);

  return {
    enabled: routing.enabled !== false,
    failover_order: ordered,
  };
}

function buildProviderConfig(config, providerId) {
  const active = providerId || config?.active_provider || 'anthropic';
  const provider = config?.providers?.[active] || {};

  let cliCommand = provider.cli_command || 'claude';
  if (!ALLOWED_CLI.has(cliCommand)) cliCommand = 'claude';

  const envVars = Object.fromEntries(
    Object.entries(provider.env_vars || {}).filter(
      ([k, v]) => v !== '' && ALLOWED_ENV_VARS.has(k)
    )
  );

  if (active === 'codex_auth' && 'OPENAI_API_KEY' in envVars) {
    delete envVars.OPENAI_API_KEY;
  }

  return {
    provider_id: active,
    cli_command: cliCommand,
    env_vars: envVars,
    active,
    provider_name: provider.name || active,
    routing: getProviderRouting(config, active),
    provider,
  };
}

function isProviderReady(providerConfig) {
  if (!providerConfig || providerConfig.active === 'none') return false;
  if (providerConfig.active === 'anthropic') return true;
  if (providerConfig.active === 'codex_auth') {
    return fs.existsSync(CODEX_AUTH_FILE);
  }

  const env = providerConfig.env_vars || {};
  const requiredKeys = Object.keys(env).filter((key) =>
    /API_KEY|TOKEN|BEARER|PROJECT_ID|AUTH_JSON_PATH/.test(key)
  );
  return requiredKeys.some((key) => Boolean((env[key] || '').trim()));
}

function supportsMode(providerConfig, mode) {
  if (!providerConfig) return false;
  if (mode === 'chat') {
    return providerConfig.active !== 'anthropic' && providerConfig.cli_command === 'openclaude';
  }
  if (mode === 'code') {
    if (providerConfig.active === 'anthropic') return true;
    return getProviderMode(providerConfig) === 'code';
  }
  return true;
}

function resolveProviderChain(mode = 'chat', preferredProviderId = null) {
  const config = loadProvidersFile();
  const routing = getProviderRouting(config, preferredProviderId || config.active_provider);
  const providers = config.providers || {};
  return routing.failover_order
    .map((providerId) => buildProviderConfig(config, providerId))
    .filter((providerConfig) => providers[providerConfig.provider_id])
    .filter((providerConfig) => supportsMode(providerConfig, mode))
    .filter((providerConfig) => isProviderReady(providerConfig));
}

function getProviderCandidates(mode = 'chat', preferredProviderId = null) {
  return resolveProviderChain(mode, preferredProviderId);
}
// ---- End TKR Customization ----

function isCodeModel(model) {
  const m = _normalizeModel(model);
  if (!m) return false;
  if (m === 'codexplan' || m === 'codexspark') return true;
  if (m.includes('memory-output') || m.includes('memory_output')) return false;
  if (m.includes('coder') || m.includes('codex') || m.includes('devstral')) return true;
  return /(^|[/:._-])code([/:._-]|$)/i.test(m);
}

function isChatCompletionModel(model) {
  const m = _normalizeModel(model);
  if (!m) return true;
  if (m.includes('memory-output') || m.includes('memory_output')) return true;
  return !isCodeModel(m);
}

function resolveProviderModel(providerConfig) {
  const env = providerConfig?.env_vars || {};
  const provider = providerConfig?.provider || {};
  const active = providerConfig?.active || 'anthropic';
  const fromEnv = (env.OPENAI_MODEL || '').trim();
  if (fromEnv) return fromEnv;
  const fromDefault = (provider.default_model || '').trim();
  if (fromDefault) return fromDefault;
  if (active === 'codex_auth') return 'codexplan';
  if (active === 'openai') return 'gpt-4.1';
  return '';
}

function getProviderMode(providerConfig) {
  const active = providerConfig?.active || 'anthropic';
  if (active === 'anthropic') return 'anthropic';
  const model = resolveProviderModel(providerConfig);
  if (isCodeModel(model)) return 'code';
  return 'chat';
}

function loadProviderConfig(providerId = null) {
  const config = loadProvidersFile();
  try {
    return buildProviderConfig(config, providerId || config.active_provider || 'anthropic');
  } catch {
    return {
      provider_id: providerId || 'anthropic',
      cli_command: 'claude',
      env_vars: {},
      active: providerId || 'anthropic',
      provider_name: providerId || 'anthropic',
      routing: { enabled: true, failover_order: [providerId || 'anthropic'] },
      provider: {},
    };
  }
}

module.exports = {
  loadProviderConfig,
  loadProvidersFile,
  resolveProviderChain,
  getProviderCandidates,
  resolveProviderModel,
  getProviderMode,
  isCodeModel,
  isChatCompletionModel,
};
