FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

ENV ARQUIVO_PT_MCP_TRANSPORT=http
ENV ARQUIVO_PT_MCP_HOST=0.0.0.0
ENV ARQUIVO_PT_MCP_PORT=7860
ENV ARQUIVO_PT_MCP_ALLOWED_HOSTS=decaf-squirrel-arquivo-pt-mcp.hf.space

EXPOSE 7860

CMD ["arquivo-pt-mcp"]
