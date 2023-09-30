#!/bin/sh

# Log all subsequent commands to logfile. FD 3 is now the console
# for things we want to show up in "docker logs".
LOGFILE=/opt/couchbase/var/lib/couchbase/logs/container-startup.log
exec 3>&1 1>>${LOGFILE} 2>&1

CONFIG_DONE_FILE=/opt/couchbase/var/lib/couchbase/container-configured
config_done() {
  touch ${CONFIG_DONE_FILE}
  echo "Couchbase Admin UI: http://localhost:8091" \
     "\nLogin credentials: Administrator / password" | tee /dev/fd/3
  echo "Stopping config-couchbase service"
  sv stop /etc/service/config-couchbase
}

if [ -e ${CONFIG_DONE_FILE} ]; then
  echo "Container previously configured." | tee /dev/fd/3
  config_done
else
  echo "Configuring Couchbase Server.  Please wait (~60 sec)..." | tee /dev/fd/3
fi

export PATH=/opt/couchbase/bin:${PATH}

wait_for_uri() {
  expected=$1
  shift
  uri=$1
  echo "Waiting for $uri to be available..."
  while true; do
    status=$(curl -s -w "%{http_code}" -o /dev/null $*)
    if [ "x$status" = "x$expected" ]; then
      break
    fi
    echo "$uri not up yet, waiting 2 seconds..."
    sleep 2
  done
  echo "$uri ready, continuing"
}

panic() {
  cat <<EOF 1>&3

@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
Error during initial configuration - aborting container
Here's the log of the configuration attempt:
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
EOF
  cat $LOGFILE 1>&3
  echo 1>&3
  kill -HUP 1
  exit
}

couchbase_cli_check() {
  couchbase-cli $* || {
    echo Previous couchbase-cli command returned error code $?
    panic
  }
}

curl_check() {
  status=$(curl -sS -w "%{http_code}" -o /tmp/curl.txt $*)
  cat /tmp/curl.txt
  rm /tmp/curl.txt
  if [ "$status" -lt 200 -o "$status" -ge 300 ]; then
    echo
    echo Previous curl command returned HTTP status $status
    panic
  fi
}

wait_for_uri 200 http://localhost:8091/ui/index.html
echo "Couchbase Server up!" | tee /dev/fd/3

echo "Set up the cluster"
couchbase_cli_check cluster-init -c localhost --cluster-name couchbase-lite-test --cluster-username Administrator \
  --cluster-password password --services data,index,query --cluster-ramsize 2560 --cluster-index-ramsize 586 --index-storage-setting default
echo

echo "Verify credentials"
curl_check http://localhost:8091/settings/web -d port=8091 -d username=Administrator -d password=password -u Administrator:password
echo

echo "Create RBAC 'admin' user"
couchbase_cli_check user-manage --set \
  -c localhost -u Administrator -p password \
  --rbac-username admin --rbac-password password \
  --auth-domain local \
  --roles 'sync_gateway_dev_ops,sync_gateway_configurator[*],mobile_sync_gateway[*],bucket_full_access[*],bucket_admin[*]'
echo

echo "Couchbase Server configured" | tee /dev/fd/3

config_done
