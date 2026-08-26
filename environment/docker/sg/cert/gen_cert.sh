#!/bin/bash -e

# This is the script for generating a self-sign certificate and key
# The final output includes
#  - sg_cert.pem // Server cert for SG config
#  - sg_key.pem  // Server private key for SG config
#  - cert.pem    // Cert in PEM format for pinning in CBL replicator
#  - cert.per    // Cert in DER format for pinning in CBL replicator

function usage 
{
  echo "Usage: ${0} -o <Output Directory>"
}

while [[ $# -gt 0 ]]
do
  key=${1}
  case $key in
      -o)
      OUTPUT_DIR=${2}
      shift
      ;;
      *)
      usage
      exit 3
      ;;
  esac
  shift
done

if [ -z "$OUTPUT_DIR" ]
then
  usage
  exit 4
fi

rm -rf ${OUTPUT_DIR}
mkdir -p ${OUTPUT_DIR}
pushd ${OUTPUT_DIR} > /dev/null

openssl genrsa -out server.key 2048
openssl req -new -sha256 -key server.key -out server.csr -subj "/CN=localhost"
openssl x509 -req -sha256 -days 3650 -in server.csr -signkey server.key -out server.pem
openssl x509 -in server.pem -out server.cer -outform DER 

cp server.pem sg_cert.pem
cp server.key sg_key.pem
cp server.pem cert.pem
cp server.cer cert.cer

rm -rf server.*

echo "Created sg_cert.pem (SG Config), sg_key.pem (SG Config), and cert.pem/cer (For pinning) ..."

popd > /dev/null