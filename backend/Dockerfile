FROM python:3.12.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd -u 10001 -r stockflow
COPY app ./app
COPY scripts ./scripts
RUN mkdir /data && chown -R 10001:10001 /data /app
USER 10001
ENV STOCKFLOW_DB_PATH=/data/stockflow.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
