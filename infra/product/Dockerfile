FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/deepaha/backend/src
LABEL org.opencontainers.image.title="DeepAha Opportunity Atlas" \
      org.opencontainers.image.version="3.8.0-rc1"
WORKDIR /opt/deepaha
COPY backend/requirements-product.txt backend/requirements-postgres.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements-postgres.txt
COPY backend/src ./backend/src
COPY web/public/product ./web/public/product
COPY RELEASE_COMPATIBILITY.json ./RELEASE_COMPATIBILITY.json
RUN useradd --uid 10001 --create-home deepaha && mkdir -p /var/lib/deepaha && chown deepaha:deepaha /var/lib/deepaha
USER deepaha
ENV DEEPAHA_DATA_DIR=/var/lib/deepaha
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=4)"
CMD ["python", "-m", "deepaha.product.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
