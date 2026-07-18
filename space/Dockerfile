# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
# yarqa Space — FastAPI + sovereign static app (vendored THREE r160, zero CDN).
FROM public.ecr.aws/docker/library/python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

ENV PYTHONUNBUFFERED=1 PORT=7860
WORKDIR /app

# Install the yarqa package itself (parent dir) plus the space requirements.
COPY pyproject.toml /app/pyproject.toml
COPY yarqa /app/yarqa
COPY space /app/space
RUN pip install --no-cache-dir --require-hashes -r space/requirements.lock && \
    pip install --no-cache-dir --no-deps --no-build-isolation -e . && \
    useradd --create-home --uid 1000 --shell /usr/sbin/nologin yarqa && \
    chown -R yarqa:yarqa /app

EXPOSE 7860
WORKDIR /app/space
USER yarqa
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import json,urllib.request; body=json.load(urllib.request.urlopen('http://127.0.0.1:7860/livez', timeout=3)); assert body.get('ok') is True and body.get('service') == 'yarqa-space' and body.get('check') == 'liveness' and body.get('yarqa_version')"
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
