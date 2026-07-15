FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir \
    -r requirements.txt \
    -i http://pypi.devneeds.ir/simple/ \
    --trusted-host pypi.devneeds.ir

COPY src ./src

ENV PYTHONPATH=/app

# Expose the HTTP port
EXPOSE 8000

CMD ["python", "src/server.py", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]