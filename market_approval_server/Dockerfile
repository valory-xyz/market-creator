FROM python:3.11.17-slim

WORKDIR /python-docker

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY market_approval_server.py .
COPY templates/ templates/

ENV FLASK_APP=market_approval_server.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0"]
