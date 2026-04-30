const { PROVIDER_METRICS_PATH, appendJsonl } = require('./platform-support');

function recordProviderEvent({
  providerId,
  event,
  model = null,
  latencyMs = null,
  success = null,
  detail = null,
  mode = null,
  metadata = null,
}) {
  try {
    return appendJsonl(PROVIDER_METRICS_PATH, {
      provider_id: providerId,
      event,
      model,
      latency_ms: latencyMs,
      success,
      detail,
      mode,
      metadata: metadata || {},
    });
  } catch {
    return null;
  }
}

module.exports = {
  recordProviderEvent,
};
