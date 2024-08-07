FROM ubuntu:22.04

ARG SG_DEB_ARM64
ARG SG_DEB_AMD64

RUN [ -z "$SG_DEB_ARM64" ] && echo "SG_DEB_ARM64 is required" && exit 1 || true
RUN [ -z "$SG_DEB_AMD64" ] && echo "SG_DEB_AMD64 is required" && exit 1 || true

RUN apt -yqq update 
RUN apt -yqq install curl

RUN mkdir -p /opt/sg && \
    ARCHITECTURE="$(dpkg --print-architecture)" && \
    if [ "$ARCHITECTURE" = "amd64" ]; then \
        curl -o /opt/sg/couchbase-sync-gateway.deb $SG_DEB_AMD64; \
    elif [ "$ARCHITECTURE" = "arm64" ]; then \
        curl -o /opt/sg/couchbase-sync-gateway.deb $SG_DEB_ARM64; \
    else \
        echo "Unsupported architecture"; \
        exit 1; \
    fi

COPY cert /opt/sg/cert
COPY config /opt/sg/config
COPY start-sgw.sh /opt/sg

WORKDIR /opt/sg

RUN apt-get update
RUN apt -yqq install systemctl
RUN dpkg -i ./couchbase-sync-gateway.deb

EXPOSE 4984
EXPOSE 4985

CMD ./start-sgw.sh
