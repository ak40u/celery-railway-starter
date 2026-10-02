FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Each of the three services overrides this with its own command; the web one
# is the default so a single-service deploy still does something sensible.
# 0.0.0.0, not ::. Uvicorn binds an IPv6 socket exclusively, and the platform's
# HTTP proxy connects over IPv4 - the symptom is a 502 with the application
# running perfectly and logging that it is listening.
CMD ["sh", "-c", "uvicorn app.web:app --host 0.0.0.0 --port ${PORT:-8080}"]
