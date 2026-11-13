#!/bin/sh
# Writes the Pi provider catalogue when this container is the Pi service, then
# execs the command. The OpenCode service sets none of these variables and the
# script is a no-op for it.
set -eu

if [ -n "${PI_PROVIDER:-}" ] && [ -n "${PI_API_KEY_ENV:-}" ]; then
    : "${PI_BASE_URL:=https://opencode.ai/zen/go/v1}"
    : "${PI_PROVIDER_NAME:=${PI_PROVIDER}}"
    : "${PI_MODEL:=deepseek-v4.1-flash}"
    : "${PI_MODEL_CONTEXT:=262144}"
    : "${PI_MODEL_MAX_TOKENS:=8192}"

    CONFIG_DIR="${HOME}/.pi/agent"
    mkdir -p "$CONFIG_DIR" "${PI_SESSION_DIR:-${DATA_DIR:-/data}/sessions}"

    cat > "$CONFIG_DIR/models.json" <<EOF
{
  "\$schema": "https://pi.dev/schemas/models.schema.json",
  "providers": {
    "${PI_PROVIDER_NAME}": {
      "baseUrl": "${PI_BASE_URL}",
      "api": "openai-completions",
      "apiKey": "\$${PI_API_KEY_ENV}",
      "models": [
        {
          "id": "${PI_MODEL}",
          "name": "${PI_MODEL}",
          "contextWindow": ${PI_MODEL_CONTEXT},
          "maxTokens": ${PI_MODEL_MAX_TOKENS}
        }
      ]
    }
  }
}
EOF
fi

exec "$@"
