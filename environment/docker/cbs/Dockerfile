ARG COUCHBASE_VERSION=7.6.4

FROM couchbase/server:enterprise-$COUCHBASE_VERSION

COPY configure-node.sh /etc/service/config-couchbase/run
RUN chmod +x /etc/service/config-couchbase/run
RUN chown -R couchbase:couchbase /etc/service