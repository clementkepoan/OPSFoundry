FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# copy dependency files first
COPY pyproject.toml README.md ./

RUN pip install --upgrade pip \
    && pip install .

# copy source code AFTER dependencies
COPY apps ./apps
COPY core ./core
COPY workflows ./workflows
COPY mcp_servers ./mcp_servers
COPY mlops ./mlops

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]