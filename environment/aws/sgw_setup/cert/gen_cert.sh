#!/bin/bash -e

CREATE_CA=0
CA_KEY="ca_key.pem"
CA_CERT="ca_cert.pem"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pushd "${SCRIPT_DIR}" >/dev/null
trap 'popd >/dev/null' EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create-ca)
      CREATE_CA=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      ;;
  esac
done

# Create OpenSSL config with SAN + wildcard.
#
# keyUsage on the CA is not optional: Python 3.13 turns on ssl.VERIFY_X509_STRICT by
# default, and strict verification rejects a CA certificate that omits it with
# "CA cert does not include key usage extension" during the TLS handshake.
cat >internal-openssl.cnf <<'EOF'
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

[ v3_ca ]
basicConstraints       = critical,CA:TRUE
keyUsage               = critical,keyCertSign,cRLSign,digitalSignature
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always

[ v3_leaf ]
basicConstraints       = critical,CA:FALSE
keyUsage               = critical,digitalSignature,keyEncipherment
extendedKeyUsage       = serverAuth
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName         = @alt_names
EOF

if [[ $CREATE_CA -eq 1 ]]; then
  echo "Creating new Private CA..."
  # Private CA
  openssl genrsa -out $CA_KEY 4096
  openssl req -x509 -new -nodes -key $CA_KEY -sha256 -days 3650 \
    -subj "/CN=Internal Test CA/O=Couchbase/C=US" \
    -extensions v3_ca -config internal-openssl.cnf -out $CA_CERT
else
  echo "Using existing Private CA..."
fi

# Server key + CSR
openssl genrsa -out sg_key.pem 4096
openssl req -new -key sg_key.pem -out server.csr -config internal-openssl.cnf

# Sign leaf cert
openssl x509 -req -in server.csr -CA $CA_CERT -CAkey $CA_KEY -CAcreateserial \
  -out sg_cert.pem -days 3650 -sha256 -extensions v3_leaf -extfile internal-openssl.cnf

# Full chain
cat sg_cert.pem $CA_CERT >sg_fullchain.pem
rm internal-openssl.cnf server.csr

# Sanity check under the same strict rules the Python test client applies
openssl verify -x509_strict -CAfile $CA_CERT sg_cert.pem

if [[ $CREATE_CA -eq 1 ]]; then
  cat <<EOF

NOTE: $CA_CERT changed.  Copy its contents into _SGW_CA_CERT in
client/src/cbltest/api/syncgateway.py -- client/tests/test_sgw_ca_cert.py fails until you do.
EOF
fi
