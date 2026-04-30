const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');

const CONFIG_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'evo-provider-config-'));
const CONFIG_PATH = path.join(CONFIG_DIR, 'providers.json');
process.env.EVO_NEXUS_PROVIDERS_PATH = CONFIG_PATH;

function loadProviderConfigModule() {
  const modulePath = require.resolve('../src/provider-config');
  delete require.cache[modulePath];
  return require(modulePath);
}

function withProviderConfig(config, fn) {
  const hadOriginal = fs.existsSync(CONFIG_PATH);
  const original = hadOriginal ? fs.readFileSync(CONFIG_PATH, 'utf8') : null;
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf8');

  try {
    return fn();
  } finally {
    if (hadOriginal) {
      fs.writeFileSync(CONFIG_PATH, original, 'utf8');
    } else if (fs.existsSync(CONFIG_PATH)) {
      fs.unlinkSync(CONFIG_PATH);
    }
  }
}

test('provider config resolves routing and ready chat candidates', () => {
  const config = {
    active_provider: 'anthropic',
    routing: {
      enabled: true,
      failover_order: ['anthropic', 'openrouter', 'openai'],
    },
    providers: {
      anthropic: {
        name: 'Anthropic',
        cli_command: 'claude',
        env_vars: {},
      },
      openrouter: {
        name: 'OpenRouter',
        cli_command: 'openclaude',
        default_base_url: 'https://openrouter.ai/api/v1',
        default_model: 'anthropic/claude-sonnet-4',
        env_vars: {
          CLAUDE_CODE_USE_OPENAI: '1',
          OPENAI_BASE_URL: '',
          OPENAI_API_KEY: 'sk-test',
          OPENAI_MODEL: '',
        },
      },
      openai: {
        name: 'OpenAI',
        cli_command: 'openclaude',
        default_model: 'gpt-4.1',
        env_vars: {
          CLAUDE_CODE_USE_OPENAI: '1',
          OPENAI_API_KEY: '',
          OPENAI_MODEL: '',
        },
      },
    },
  };

  withProviderConfig(config, () => {
    const {
      getProviderCandidates,
      getProviderMode,
      loadProviderConfig,
      resolveProviderChain,
      resolveProviderModel,
    } = loadProviderConfigModule();

    const active = loadProviderConfig();
    assert.equal(active.provider_id, 'anthropic');
    assert.equal(active.routing.enabled, true);
    assert.deepEqual(active.routing.failover_order[0], 'anthropic');

    const openrouter = loadProviderConfig('openrouter');
    assert.equal(resolveProviderModel(openrouter), 'anthropic/claude-sonnet-4');
    assert.equal(openrouter.env_vars.OPENAI_BASE_URL, 'https://openrouter.ai/api/v1');
    assert.equal(openrouter.env_vars.OPENAI_MODEL, 'anthropic/claude-sonnet-4');
    assert.equal(getProviderMode(openrouter), 'code');

    const chain = resolveProviderChain('code', 'openrouter');
    assert.equal(chain[0].provider_id, 'openrouter');

    const candidates = getProviderCandidates('chat', 'anthropic');
    assert.deepEqual(candidates.map((candidate) => candidate.provider_id), ['openrouter']);
  });
});

test('non-anthropic code routing does not silently fall back to native claude', () => {
  const config = {
    active_provider: 'openrouter',
    routing: {
      enabled: true,
      failover_order: ['openrouter', 'anthropic'],
    },
    providers: {
      anthropic: {
        name: 'Anthropic',
        cli_command: 'claude',
        env_vars: {},
      },
      openrouter: {
        name: 'OpenRouter',
        cli_command: 'openclaude',
        default_base_url: 'https://openrouter.ai/api/v1',
        default_model: 'anthropic/claude-sonnet-4',
        env_vars: {
          CLAUDE_CODE_USE_OPENAI: '1',
          OPENAI_BASE_URL: '',
          OPENAI_API_KEY: '',
          OPENAI_MODEL: '',
        },
      },
    },
  };

  withProviderConfig(config, () => {
    const { resolveProviderChain } = loadProviderConfigModule();
    const chain = resolveProviderChain('code', 'openrouter');
    assert.deepEqual(chain.map((candidate) => candidate.provider_id), []);
  });
});
