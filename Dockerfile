FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py database.py http_client.py main.py models.py repository.py toss_auth.py ./
COPY collectors ./collectors
COPY sql ./sql

ENV PYTHONUNBUFFERED=1

USER 65532:65532

CMD ["python", "main.py"]
