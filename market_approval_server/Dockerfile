FROM python:3.11-slim

WORKDIR /python-docker

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Only the server is copied. The state file lives on a mounted volume, at the
# path given by MARKET_APPROVAL_SERVER_CONFIG_FILE, and is never part of the image.
COPY market_approval_server.py .
COPY templates/ templates/

ENV FLASK_APP=market_approval_server.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0"]
