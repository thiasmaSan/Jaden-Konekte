FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY simulateur_capteurs.py .
USER 1000
CMD ["python", "simulateur_capteurs.py", "--help"]
