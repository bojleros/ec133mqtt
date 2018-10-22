FROM alpine:3.8

RUN apk --no-cache add mosquitto-clients py3-paho-mqtt && \
    apk add --no-cache --repository http://nl.alpinelinux.org/alpine/edge/testing py3-serial && \
    pip3 install modbus-tk && \
    rm -rf /var/cache/apk/*

ENV APP_DIR /app

COPY app/* /app/

WORKDIR /app

ENTRYPOINT ["python3"]

CMD ["-u", "main.py"]
