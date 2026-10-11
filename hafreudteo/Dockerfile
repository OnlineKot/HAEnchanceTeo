ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM $BUILD_FROM

LABEL maintainer="TeodorTeo.com <https://teodorteo.com>"

RUN apk add --no-cache python3 py3-aiohttp

COPY run.sh /run.sh
COPY app /app
RUN chmod a+x /run.sh

CMD ["/run.sh"]
