FROM python:3.8-slim-buster

WORKDIR /python-docker

RUN pip3 install flask

COPY . .

ENV FLASK_APP=market_approval_server.py

EXPOSE 5000

CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]