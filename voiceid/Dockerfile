FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /service
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./

ENV SPEAKER_ID_PORT=8788
EXPOSE 8788
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8788}"]
