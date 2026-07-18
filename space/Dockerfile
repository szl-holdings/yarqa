# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
# yarqa Space — FastAPI + sovereign static app (vendored THREE r160, zero CDN).
FROM public.ecr.aws/docker/library/python:3.11-slim

ENV PYTHONUNBUFFERED=1 PORT=7860
WORKDIR /app

# Install the yarqa package itself (parent dir) plus the space requirements.
COPY pyproject.toml /app/pyproject.toml
COPY yarqa /app/yarqa
COPY space /app/space
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir -r space/requirements.txt

EXPOSE 7860
WORKDIR /app/space
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
