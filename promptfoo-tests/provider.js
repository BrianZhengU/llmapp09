// Custom promptfoo provider for the LLM Multi-Route API.
// Each test sets vars.task (summarize, sentiment, support, ...) and the provider
// POSTs the rendered prompt to {baseUrl}/api/<task>.
// Docs: https://www.promptfoo.dev/docs/providers/custom-api/

const BODY_BUILDERS = {
  chat: (text) => ({ message: text }),
  support: (text) => ({ message: text }),
  generate: (text, vars) => ({ prompt: text, tone: vars.tone || 'professional' }),
  // categories is a comma-separated string: promptfoo would expand an array var into several tests.
  classify: (text, vars) => ({
    text,
    categories: vars.categories ? String(vars.categories).split(',').map((c) => c.trim()) : null,
  }),
};

class MultiRouteProvider {
  constructor(options = {}) {
    this.providerId = options.id || 'llm-multiroute';
    this.config = options.config || {};
  }

  id() {
    return this.providerId;
  }

  async callApi(prompt, context) {
    const vars = (context && context.vars) || {};
    const task = vars.task || 'chat';
    const baseUrl = (process.env.API_BASE_URL || this.config.baseUrl || 'http://localhost:8080').replace(/\/$/, '');
    const build = BODY_BUILDERS[task] || ((text) => ({ text }));

    try {
      const resp = await fetch(`${baseUrl}/api/${task}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(build(prompt, vars)),
      });
      const data = await resp.json();
      if (!resp.ok) {
        // Guardrail blocks (HTTP 400) are a valid, testable outcome, so return them as output.
        return { output: JSON.stringify({ status: resp.status, ...data }), metadata: { status: resp.status } };
      }
      // For routing tests, expose the routing decision as JSON so assertions can check it.
      const output = task === 'support'
        ? JSON.stringify({ label: data.label, routed_to: data.routed_to, output: data.output })
        : data.output;
      return { output, metadata: { model: data.model, latency_ms: data.latency_ms, status: resp.status } };
    } catch (err) {
      return { error: `Request to ${baseUrl}/api/${task} failed: ${err.message}` };
    }
  }
}

module.exports = MultiRouteProvider;
