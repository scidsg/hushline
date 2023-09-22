FROM python:3-alpine

RUN apk --no-cache -U upgrade

COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt

EXPOSE 5000
ENV FLASK_APP=app
CMD ["flask", "run", "-h", "0.0.0.0", "-p", "80"]