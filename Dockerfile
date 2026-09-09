FROM node:22-bookworm-slim AS frontend
ARG CODEX_CLI_VERSION=0.153.4
RUN npm install --global "@openai/codex@${CODEX_CLI_VERSION}"
WORKDIR /app/runtime
COPY runtime/package*.json ./
RUN npm ci
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# akshare pulls the legacy package into the same module directory; keep mini-racer.
RUN pip uninstall -y py-mini-racer && pip install --no-cache-dir --force-reinstall --no-deps 'mini-racer>=0.12' \
    && python -c "from py_mini_racer import MiniRacer; ctx = MiniRacer(); assert ctx.eval('1 + 1') == 2"
RUN useradd --create-home --uid 1000 app
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules/@openai/codex /usr/local/lib/node_modules/@openai/codex
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex \
    && codex --version
COPY main.py server.py sharing.py sharing_schema.py sharing_worker.py sharing_admin.py ./
COPY --from=frontend /app/runtime /app/runtime
COPY review_agent/ ./review_agent/
COPY backtest/ ./backtest/
COPY research_data/ ./research_data/
COPY duanxian/ ./duanxian/
COPY vr/ ./vr/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN mkdir -p /app/vr/.cache && chown app:app /app/vr/.cache
USER app
EXPOSE 8910
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8910"]
