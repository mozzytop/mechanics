FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces (Docker SDK) expects the app to listen on 7860.
# A writable data dir is required since Spaces containers run as a non-root
# user with a read-only image filesystem outside of specific paths.
RUN mkdir -p /data && chmod 777 /data
ENV DATABASE_PATH=/data/virtual_mechanic.db
ENV PORT=7860

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
