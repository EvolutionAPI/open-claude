const fs = require('fs');
const path = require('path');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..', '..');
const PROVIDERS_PATH = process.env.EVO_NEXUS_PROVIDERS_PATH ||
  path.join(WORKSPACE_ROOT, 'config', 'providers.json');
const CODEX_AUTH_FILE = path.join(
  process.env.CODEX_HOME || path.join(process.env.HOME || '/', '.codex'),
  'auth.json',
);

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
  'openrouter',
  'anthropic',
  'openai',
  'codex_auth',
  'gemini',
  'bedrock',
  'vertex',
];

const PROVIDER_DEFAULT_ENV = {
  openrouter: {
    OPENAI_BASE_URL: 'https://openrouter.ai/api/v1',
  },
};

function _normalizeModel(model) {
  return (model || '').trim().toLowerCase();
}

function loadProvidersFile() {
  try {
    if (!fs.existsSync(PROVIDERS_PATH)) {
      return { active_provider: 'openrouter', providers: {} };
    }
    return JSON.parse(fs.readFileSync(PROVIDERS_PATH, 'utf8'));
  } catch {
    return { active_provider: 'openrouter', providers: {} };
  }
}

function getProviderRouting(config, activeProviderId = null) {
  const providers = config?.providers || {};
  const active = activeProviderId || config?.active_provider || 'openrouter';
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
  const active = providerId || config?.active_provider || 'openrouter';
  const provider = config?.providers?.[active] || {};

  let cliCommand = provider.cli_command || 'claude';
  if (!ALLOWED_CLI.has(cliCommand)) cliCommand = 'claude';

  const rawEnvVars = provider.env_vars || {};
  const envVars = Object.fromEntries(
    Object.entries(rawEnvVars).filter(
      ([k, v]) => v !== '' && ALLOWED_ENV_VARS.has(k)
    )
  );

  const providerDefaults = PROVIDER_DEFAULT_ENV[active] || {};
  if ('OPENAI_BASE_URL' in rawEnvVars && !envVars.OPENAI_BASE_URL) {
    const defaultBaseUrl = provider.default_base_url || providerDefaults.OPENAI_BASE_URL;
    if (defaultBaseUrl) envVars.OPENAI_BASE_URL = defaultBaseUrl;
  }
  if ('OPENAI_MODEL' in rawEnvVars && !envVars.OPENAI_MODEL && provider.default_model) {
    envVars.OPENAI_MODEL = provider.default_model;
  }
  if ('GEMINI_MODEL' in rawEnvVars && !envVars.GEMINI_MODEL && provider.default_model) {
    envVars.GEMINI_MODEL = provider.default_model;
  }

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
    const explicitAuthPath = providerConfig.env_vars?.CODEX_AUTH_JSON_PATH;
    return fs.existsSync(explicitAuthPath || CODEX_AUTH_FILE);
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
    return providerConfig.cli_command === 'openclaude' && getProviderMode(providerConfig) === 'code';
  }
  return true;
}

function resolveProviderChain(mode = 'chat', preferredProviderId = null) {
  const config = loadProvidersFile();
  const preferred = preferredProviderId || config.active_provider;
  const routing = getProviderRouting(config, preferred);
  const providers = config.providers || {};
  const chain = routing.failover_order
    .map((providerId) => buildProviderConfig(config, providerId))
    .filter((providerConfig) => providers[providerConfig.provider_id])
    .filter((providerConfig) => supportsMode(providerConfig, mode))
    .filter((providerConfig) => isProviderReady(providerConfig));

  if (mode === 'code' && preferred && preferred !== 'anthropic') {
    const openClaudeChain = chain.filter(
      (providerConfig) =>
        providerConfig.provider_id === preferred ||
        providerConfig.cli_command === 'openclaude'
    );
    return openClaudeChain.length > 0 ? openClaudeChain : chain.filter(
      (providerConfig) => providerConfig.provider_id === preferred
    );
  }

  return chain;
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
  if (m.includes('claude') || m.includes('sonnet') || m.includes('opus') || m.includes('haiku')) return true;
  if (m.includes('gpt-5') || m.includes('gpt-4') || m.includes('gpt-4o') || m.includes('gpt-4.1')) return true;
  if (/^o[134]($|[/:._-])/.test(m)) return true;
  if (m.includes('gemini-2.5') || m.includes('qwen3-coder') || m.includes('deepseek') || m.includes('kimi-k2')) return true;
  if (m.includes('glm-4.5')) return true;
  return /(^|[/:._-])code([/:._-]|$)/i.test(m);
}

function isChatCompletionModel(model) {
  const m = _normalizeModel(model);
  if (!m) return false;
  if (m.includes('memory-output') || m.includes('memory_output')) return true;
  return ['embedding', 'moderation', 'whisper', 'tts', 'dall-e', 'image', 'audio', 'rerank'].some(
    (token) => m.includes(token)
  );
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
  if (isChatCompletionModel(model)) return 'chat';
  if (isCodeModel(model)) return 'code';
  return providerConfig?.cli_command === 'openclaude' ? 'code' : 'chat';
}

function loadProviderConfig(providerId = null) {
  const config = loadProvidersFile();
  try {
    return buildProviderConfig(config, providerId || config.active_provider || 'openrouter');
  } catch {
    return {
      provider_id: providerId || 'openrouter',
      cli_command: 'openclaude',
      env_vars: {},
      active: providerId || 'openrouter',
      provider_name: providerId || 'openrouter',
      routing: { enabled: true, failover_order: [providerId || 'openrouter'] },
      provider: {},
    };
  }
}

/**
 * Watch providers.json for active_provider changes.
 * Calls onChange(newActiveProvider, oldActiveProvider) when the provider switches.
 * Returns a stop() function to cancel watching.
 */
function watchProviderChanges(onChange) {
  let lastKnownProvider = null;
  try {
    const config = loadProvidersFile();
    lastKnownProvider = config.active_provider || 'openrouter';
  } catch {
    lastKnownProvider = 'openrouter';
  }

  const POLL_INTERVAL_MS = 2000;
  const interval = setInterval(() => {
    try {
      const config = loadProvidersFile();
      const currentProvider = config.active_provider || 'openrouter';
      if (currentProvider !== lastKnownProvider) {
        const oldProvider = lastKnownProvider;
        lastKnownProvider = currentProvider;
        console.log(`[provider-watcher] Provider changed: ${oldProvider} -> ${currentProvider}`);
        if (onChange) onChange(currentProvider, oldProvider);
      }
    } catch (err) {
      // Ignore transient read errors (file being written)
    }
  }, POLL_INTERVAL_MS);

  if (typeof interval.unref === 'function') {
    interval.unref();
  }

  return {
    stop() {
      clearInterval(interval);
    },
    getCurrentProvider() {
      return lastKnownProvider;
    },
  };
}

module.exports = {
  loadProviderConfig,
  loadProvidersFile,
  resolveProviderChain,
  getProviderCandidates,
  resolveProviderModel,
  getProviderMode,
  isProviderReady,
  isCodeModel,
  isChatCompletionModel,
  watchProviderChanges,
};
