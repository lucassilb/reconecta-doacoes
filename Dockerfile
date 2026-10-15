FROM python:3.14-alpine@sha256:f6a589d43c42b9e7f7dc67a12d37132491f362859a5d750607710cc56da3bc72

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apk upgrade --no-cache && pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y pip \
    && adduser -D -H -u 10001 reconecta

COPY --chown=reconecta:reconecta . /app
RUN mkdir -p /app/instance && chown reconecta:reconecta /app/instance
USER reconecta

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '5000') + '/reconecta/saude', timeout=4)" || exit 1

CMD ["sh", "-c", "exec gunicorn app:app --preload --worker-class gthread --threads 8 --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 90 --access-logfile - --error-logfile -"]
