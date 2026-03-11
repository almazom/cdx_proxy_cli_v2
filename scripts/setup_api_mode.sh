#!/bin/bash
# Setup script to use cdx proxy with codex in API mode

echo "=== CDX Proxy + Codex API Mode Setup ==="
echo

# Check if we have API keys
if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY not set"
    echo
    echo "To use the proxy with codex, you need:"
    echo "1. OpenAI API keys from https://platform.openai.com/api-keys"
    echo "2. Add them to the proxy auth directory"
    echo
    echo "Example:"
    echo 'echo "{\"auth_mode\": \"api\", \"OPENAI_API_KEY\": \"sk-...\"}" > ~/.codex/_auths/api_key_1.json'
    echo
    exit 1
fi

# Start proxy
echo "Starting proxy..."
cdx proxy --auth-dir ~/.codex/_auths

# Export proxy settings
echo "Setting up environment..."
export OPENAI_BASE_URL="http://127.0.0.1:42209"
export OPENAI_API_BASE="http://127.0.0.1:42209"

echo
echo "=== Setup Complete ==="
echo "Proxy running at: http://127.0.0.1:42209"
echo
echo "To use codex with proxy, run:"
echo '  export OPENAI_API_KEY="your-api-key"'
echo '  export OPENAI_BASE_URL="http://127.0.0.1:42209"'
echo '  codex exec "your prompt"'
