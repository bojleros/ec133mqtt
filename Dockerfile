FROM alpine:3.20

RUN apk --no-cache add mosquitto-clients py3-paho-mqtt  py3-pyserial && \
    apk add --no-cache --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing py3-modbus-tk && \
    rm -rf /var/cache/apk/*

ENV APP_DIR /app

COPY app/* /app/

WORKDIR /app

ENTRYPOINT ["python3"]

CMD ["-u", "main.py"]
