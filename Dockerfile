# Container image for the nickol-knx-mcp stdio MCP server.
# Used by Glama (https://glama.ai) to start the server and run MCP introspection.
FROM python:3.12-slim

WORKDIR /app

# Install the package (and its deps) from source
COPY pyproject.toml README.md ./
COPY nickol_knx_mcp ./nickol_knx_mcp
RUN pip install --no-cache-dir .

# Confined output workspace (the server only ever writes here; no bus access)
ENV NICKOL_KNX_WORKSPACE=/workspace
RUN mkdir -p /workspace

# stdio MCP server — Glama pipes JSON-RPC over stdin/stdout for introspection
ENTRYPOINT ["nickol-knx-mcp"]
