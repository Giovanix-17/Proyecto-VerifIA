# VerifIA — imagen única: FastAPI + Tesseract (español) + modelos spaCy.
# Fuente: VerifIA_memoria_proyecto.md §9 Fase 7 y skill verifia-api-docker.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    PYTHONPATH=/app/src

# Tesseract con el paquete de español; libgl/libglib para OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      tesseract-ocr-spa \
      libgl1 \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Capa de dependencias separada: solo se reconstruye si cambian los requisitos.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -m spacy download es_core_news_md

COPY . .

# Usuario sin privilegios (se combina con read_only en docker-compose).
RUN useradd --create-home verifia && chown -R verifia:verifia /app
USER verifia

EXPOSE 8000

CMD ["uvicorn", "verifia.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
