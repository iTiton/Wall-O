FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wallo ./wallo
# Necesita el socket de Docker (montado en docker-compose.yml) para despertar y dormir herramientas
EXPOSE 8100
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/api/herramientas' % os.environ.get('WALLO_PUERTO','8100'))" || exit 1
CMD ["python", "-m", "wallo"]
