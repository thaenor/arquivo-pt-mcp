FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir arquivo-pt-mcp

ENV ARQUIVO_PT_MCP_TRANSPORT=http
ENV ARQUIVO_PT_MCP_HOST=0.0.0.0
ENV ARQUIVO_PT_MCP_PORT=8000
ENV ARQUIVO_PT_MCP_ALLOWED_HOSTS=decaf-squirrel-arquivo-pt-mcp.hf.space

EXPOSE 8000

CMD ["arquivo-pt-mcp"]
