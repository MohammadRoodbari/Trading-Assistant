FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir \
    -r requirements.txt \
    -i http://pypi.devneeds.ir/simple/ \
    --trusted-host pypi.devneeds.ir

# Copy the whole src directory
COPY src ./src

# Make the src directory importable
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.server"]