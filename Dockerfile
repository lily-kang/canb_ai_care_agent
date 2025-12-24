FROM python:3.12-slim

# Python 런타임 기본 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# (필요 시) 빌드 도구 등 최소한의 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 비-root 유저로 실행 (보안상 권장)
RUN useradd -m appuser
USER appuser

EXPOSE 8080

# Cloud Run 에서 FastAPI 앱 실행
CMD ["uvicorn", "sp_agent_app.main:app", "--host", "0.0.0.0", "--port", "8080"]

