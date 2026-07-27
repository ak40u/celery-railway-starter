FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Each of the three services overrides this with its own command; the web one
# is the default so a single-service deploy still does something sensible.
CMD ["sh", "-c", "uvicorn app.web:app --host :: --port ${PORT:-8080}"]
