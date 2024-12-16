ARG COUCHBASE_VERSION=7.1.4
ARG COUCHBASE_CONTAINER_PATH="couchbase/server:enterprise-"

FROM ${COUCHBASE_CONTAINER_PATH}${COUCHBASE_VERSION}

COPY configure-node.sh /etc/service/config-couchbase/run
RUN chmod +x /etc/service/config-couchbase/run
RUN chown -R couchbase:couchbase /etc/service
