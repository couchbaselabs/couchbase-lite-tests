#!/bin/bash -e

DOMAIN="compute-1.amazonaws.com"
WILDCARD="*.compute-1.amazonaws.com"
CREATE_CA=0
CA_KEY="ca_key.pem"
CA_CERT="../../../dataset/sg/ca_cert.pem"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pushd "${SCRIPT_DIR}" > /dev/null

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create-ca)
      CREATE_CA=1; shift ;;
    *)
      echo "Unknown option: $1" ;;
  esac
done

# Create OpenSSL config with SAN + wildcard
cat > internal-openssl.cnf <<'EOF'
[ req ]
default_bits       = 4096
prompt             = no
default_md         = sha256
req_extensions     = req_ext
distinguished_name = dn

[ dn ]
CN = compute-1.amazonaws.com

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = compute-1.amazonaws.com
DNS.2 = *.compute-1.amazonaws.com
EOF

if [[ $CREATE_CA -eq 1 ]]; then
  echo "Creating new Private CA..."
  # Private CA
  openssl genrsa -out $CA_KEY 4096
  openssl req -x509 -new -nodes -key $CA_KEY -sha256 -days 730 \
    -subj "/CN=Internal Test CA/O=Couchbase/C=US" -out ../../../dataset/certs/$CA_CERT
else
  echo "Using existing Private CA..."
fi

# Server key + CSR
openssl genrsa -out sg_key.pem 4096
openssl req -new -key sg_key.pem -out server.csr -config internal-openssl.cnf

# Sign leaf cert
openssl x509 -req -in server.csr -CA ca_cert.pem -CAkey ca_key.pem -CAcreateserial \
  -out sg_cert.pem -days 365 -sha256 -extensions req_ext -extfile internal-openssl.cnf

# Full chain
cat sg_cert.pem ca_cert.pem > sg_fullchain.pem
rm internal-openssl.cnf server.csr