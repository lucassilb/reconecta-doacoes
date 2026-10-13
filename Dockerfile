FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y pip \
    && useradd --system --create-home --uid 10001 reconecta

COPY --chown=reconecta:reconecta . /app
RUN mkdir -p /app/instance && chown reconecta:reconecta /app/instance
USER reconecta

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '5000') + '/reconecta/saude', timeout=4)" || exit 1

CMD ["sh", "-c", "exec gunicorn app:app --preload --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 90 --access-logfile - --error-logfile -"]
