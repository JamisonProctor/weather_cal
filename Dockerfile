FROM python:3.11-slim-bullseye AS builder
WORKDIR /app
COPY requirements.txt .
# Install dependencies to a custom folder for later copy
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --prefix=/app/deps -r requirements.txt
COPY . .

FROM builder AS permfix
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /app/data && chown -R 65532:65532 /app/data

FROM gcr.io/distroless/python3-debian11
WORKDIR /app
COPY --from=permfix /app /app
COPY --from=permfix /app/deps /app/deps
COPY --from=permfix /usr/share/zoneinfo/Europe/Berlin /etc/localtime
COPY --from=permfix /etc/timezone /etc/timezone

ENV PYTHONPATH=/app/deps/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin

USER 65532:65532
CMD ["main.py"]