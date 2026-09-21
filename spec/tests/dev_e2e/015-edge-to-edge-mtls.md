# Test Cases

These tests validate Edge Server (ES) to Edge Server replication authenticated
with a TLS **client certificate** (mutual TLS / mTLS).

A **source** ES replicates to a **target** ES over mTLS: the source presents a
client certificate (`auth.tls_client_cert` / `auth.tls_client_cert_key`) and the
target verifies incoming clients against a CA (`https.client_cert_path`). The
client certificate and key are supplied as **file paths** in a config-file
`replications` block, matching the customer deployment that reported the issue.

Each test generates its own X.509 material in-memory with `cert_helper.py`: a CA,
a target **server** certificate whose SubjectAltName is the target host (so the
source can verify it against `trusted_root_certs`), and a **client**
certificate/key. The client key is a plain, unencrypted PKCS#8 PEM key.

This is the regression test for CBL-8862: Edge Server 1.1.0 parsed the PEM
replication client key with `mbedtls_pk_parse_key(..., size())` instead of
`size() + 1` (sockpp `mbedtls_context::set_identity`), so the PEM key was misread
as DER and failed with `PK - Invalid key tag or value`. Fixed in LiteCore 3.3.4.

Requires a topology with at least 2 Edge Servers.

## test_edge_to_edge_mtls_replication

### Description

Verify that a source Edge Server can replicate to a target Edge Server over
mutual TLS, with the source's client certificate and key given as file paths in a
config-file `replications` block. The replication must reach a healthy running
state (Idle or Busy) with no error, which requires the source to successfully load
and present the PEM client key during the TLS handshake.

### Steps

1. Take two Edge Servers from the topology: `source` (the replication client) and `target` (the passive mTLS server).
2. Generate a CA, a target server certificate (SubjectAltName = the target host), and a client certificate with an unencrypted PEM key.
3. Write the CA, server certificate, and server key to the target host, and start the target with an mTLS `https` config (`tls_cert_path`, `tls_key_path`, `client_cert_path` = the CA).
4. Write the CA and the client certificate/key to the source host.
5. Configure and start the source with a config-file `replications` block whose `target` is `wss://<target host>:59840/db`, `auth.tls_client_cert` / `tls_client_cert_key` point at the client cert/key file paths, and `trusted_root_certs` points at the CA.
6. Wait until the source's replication reaches `Idle` or `Busy`.
7. Verify the replication is in `Idle`/`Busy` state and reports no error (confirming the PEM client key loaded and the mTLS handshake succeeded).
