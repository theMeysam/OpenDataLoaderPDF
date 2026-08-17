FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set JVM memory options only after Java installation. Debian's
# ca-certificates-java post-install scripts invoke Java with their own small
# heap limit, so defining JAVA_TOOL_OPTIONS earlier can break apt/dpkg.
ENV JAVA_TOOL_OPTIONS="-Xmx1536m"

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app.py ./

EXPOSE 7860

CMD ["python", "app.py"]
