FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/ec2-user

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl jq unzip procps \
    && rm -rf /var/lib/apt/lists/*

ARG ES_DEB=https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-edge-server/1.2.0/4/couchbase-edge-server_1.2.0-4_amd64.deb
RUN curl -fsSL -o /tmp/couchbase-edge-server.deb "$ES_DEB" \
    && dpkg -i /tmp/couchbase-edge-server.deb \
    && rm /tmp/couchbase-edge-server.deb

ARG SHELL2HTTP_URL=https://github.com/msoap/shell2http/releases/download/v1.17.0/shell2http_1.17.0_linux_amd64.tar.gz
RUN curl -fsSL -o /tmp/shell2http.tar.gz "$SHELL2HTTP_URL" \
    && tar -xzf /tmp/shell2http.tar.gz -C /usr/local/bin shell2http \
    && rm /tmp/shell2http.tar.gz

RUN mkdir -p /home/ec2-user/database \
             /home/ec2-user/cert \
             /home/ec2-user/user \
             /home/ec2-user/log \
             /opt/couchbase-edge-server/etc \
             /opt/es-default \
             /opt/es-scripts

COPY users.json /home/ec2-user/user/users.json
COPY config.json /opt/es-default/config.json
COPY common.sh add-user.sh reset-db.sh write-file.sh \
     start-edgeserver.sh kill-edgeserver.sh start.sh \
     /opt/es-scripts/
RUN chmod +x /opt/es-scripts/*.sh

WORKDIR /home/ec2-user
EXPOSE 59840 20001
CMD ["/opt/es-scripts/start.sh"]
