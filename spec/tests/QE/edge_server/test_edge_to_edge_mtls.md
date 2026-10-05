# Edge Server to Edge Server mTLS Tests

These tests validate Edge Server (ES) to Edge Server replication over mutual TLS when the
certificates and keys are in DER (binary) form as well as PEM, and that the target really does
enforce client certificates.

## test_edge_to_edge_mtls_formats

### Description

Test that bidirectional replication works over mTLS for each combination of formats below, with
documents crossing in both directions.

| Parameter | Target cert / key | Target client CA | Source client cert / key |
|---|---|---|---|
| `client_cert_der_key_der` | PEM / PEM | PEM | DER / DER |
| `client_cert_pem_key_der` | PEM / PEM | PEM | PEM / DER |
| `client_cert_der_key_pem` | PEM / PEM | PEM | DER / PEM |
| `server_der` | DER / DER | PEM | PEM / PEM |
| `all_der` | DER / DER | DER | DER / DER |

The mixed client cases pin a failure to the certificate parse or to the key parse, which are
separate code paths. `server_der` covers the DER support the server-TLS docs promise. `all_der`
covers the target's client CA, whose format is undocumented.

### Steps

1. Generate the CA, target server certificate, source client certificate and framework client certificate.
2. Install the CA and framework certificate as the harness's `~/.cbl_certs` identity.
3. Write the target's certificate, key and client CA in the parameter's formats, and start the target with mTLS.
4. Verify the target accepts a TLS client presenting the framework certificate and refuses one presenting none.
5. Write `<case>_target_seed` to the target.
6. Write the source's client certificate and key in the parameter's formats and the CA as PEM, and start the source replicating to the target.
7. Wait for the source's replicator to exist, report no error, and be `Idle`.
8. Verify `<case>_target_seed` is on the source.
9. Write `<case>_source_write` to the source and wait for it to reach the target.

## test_edge_to_edge_mtls_rejects_client

### Description

Test that the target refuses a source whose client identity it should not accept, and that doing
so does not take the target down. The target's material is PEM, since verification happens on the
target and does not depend on the format the source read its files in.

| Parameter | Source client identity |
|---|---|
| `no_client_cert` | None: the replication has no `auth` block |
| `untrusted_ca` | A certificate signed by a CA the target does not trust |
| `expired_client_cert` | A certificate signed by the trusted CA, but expired a day ago |

### Steps

1. Generate the CA, target server certificate and framework client certificate, and the parameter's client identity.
2. Install the CA and framework certificate as the harness's `~/.cbl_certs` identity.
3. Write the target's certificate, key and client CA as PEM, and start the target with mTLS.
4. Verify the target accepts a TLS client presenting the framework certificate and refuses one presenting none.
5. Write `<case>_target_seed` to the target.
6. Start the source replicating to the target with the parameter's client identity.
7. Wait for the source's replicator to give up: removed, `Stopped`/`Offline`, or reporting an error.
8. Verify `<case>_target_seed` is not on the source.
9. Verify the target still serves requests.
