# Edge Server with the same Caddy and shell2http sidecars as an AWS host, laid out under
# /home/ec2-user so the paths in test configs resolve unchanged.
# Built by start_edge_server.py, which stages the build context.
FROM amazonlinux:2023

ARG TARGETARCH
ARG CADDY_VERSION=2.10.2
ARG SHELL2HTTP_VERSION=1.17.0

RUN dnf install -y --allowerasing \
    coreutils findutils gzip iproute iptables-nft jq procps-ng shadow-utils socat sudo tar unzip util-linux \
  && dnf clean all

RUN useradd -m ec2-user \
  && echo 'ec2-user ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/ec2-user

COPY edge-server.rpm /tmp/edge-server.rpm
RUN dnf install -y /tmp/edge-server.rpm \
  && dnf clean all \
  && rm /tmp/edge-server.rpm \
  && chown -R ec2-user /opt/couchbase-edge-server/etc

USER ec2-user
WORKDIR /home/ec2-user

RUN mkdir -p audit cert database log shell2http user \
  && curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz caddy \
  && curl -fsSL "https://github.com/msoap/shell2http/releases/download/v${SHELL2HTTP_VERSION}/shell2http_${SHELL2HTTP_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz -C shell2http shell2http

COPY --chown=ec2-user Caddyfile entrypoint.sh ./
COPY --chown=ec2-user shell2http/ shell2http/
COPY --chown=ec2-user dataset/ database/
COPY --chown=ec2-user config.json /opt/couchbase-edge-server/etc/config.json
# Last, since a fresh CA is minted on every run.
COPY --chown=ec2-user cert/ cert/

EXPOSE 59840 20000 20001
ENTRYPOINT ["bash", "/home/ec2-user/entrypoint.sh"]
