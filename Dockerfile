FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openjdk-17-jre-headless \
       ca-certificates \
       tesseract-ocr \
       tesseract-ocr-fas \
       tesseract-ocr-ara \
       tesseract-ocr-eng \
       libgomp1 \
       libgl1 \
       libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set JVM memory options only after Java installation. Debian's
# ca-certificates-java post-install scripts invoke Java during package setup.
ENV JAVA_TOOL_OPTIONS="-Xmx1536m"

WORKDIR /app

COPY requirements.txt ./

# Install CPU-only PyTorch first. Without this, pip may resolve the default
# CUDA-enabled PyTorch stack and download several GB of NVIDIA packages even
# though this CapRover host runs the OCR backend on CPU.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu \
       torch==2.13.0 torchvision==0.28.0 \
    && pip install -r requirements.txt

COPY app.py ./

EXPOSE 7860

CMD ["python", "app.py"]