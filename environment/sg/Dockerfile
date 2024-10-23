FROM ubuntu:22.04

SHELL ["/bin/bash", "-c"]
RUN apt -yqq update 
RUN apt -yqq install curl systemctl
RUN mkdir -p /opt/sg
COPY cert /opt/sg/cert
COPY config /opt/sg/config
COPY start-sgw.sh /opt/sg

ARG SG_DEB
RUN [ -z "$SG_DEB" ] && echo "SG_DEB is required" && exit 1 || true
RUN ARCHITECTURE="$(dpkg --print-architecture)" && \
    if [ "$ARCHITECTURE" = "amd64" ]; then \
        curl -o /opt/sg/couchbase-sync-gateway.deb ${SG_DEB/<ARCH>/x86_64}; \
    elif [ "$ARCHITECTURE" = "arm64" ]; then \
        curl -o /opt/sg/couchbase-sync-gateway.deb ${SG_DEB/<ARCH>/aarch64}; \
    else \
        echo "Unsupported architecture"; \
        exit 1; \
    fi

WORKDIR /opt/sg
RUN dpkg -i ./couchbase-sync-gateway.deb

EXPOSE 4984
EXPOSE 4985

CMD ./start-sgw.sh
