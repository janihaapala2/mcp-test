FROM docker.io/library/python:3.12-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY server-movies.py .

# Default: STDIO transport (best for "docker run -i")
#ENV MCP_TRANSPORT=http
ENV MCP_TRANSPORT=stdio

# Streamable HTTP uses port 8000 by default in typical examples/configs. :contentReference[oaicite:8]{index=8}
EXPOSE 8000

ENTRYPOINT ["python", "server-movies.py"]
