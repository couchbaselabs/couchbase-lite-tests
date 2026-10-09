# Edge-to-Edge mTLS Tests (Edge Server)

## test_edge_to_edge_mtls_formats

**Steps:**
1. Create a CA, a target server certificate, a source client certificate and a framework client certificate, all signed by the CA.
2. Install the CA and framework client certificate in `~/.cbl_certs` so the test framework can reach the mTLS target.
3. Start the target Edge Server with mTLS:
   * Write the server cert, server key and client CA in `server_format` (`pem` or `der`)
   * config: `test_e2e_mtls_target.json` with `https` set to those files
4. Create document `seed_<server_format>_<client_format>` on the target `db`.
5. Start the source Edge Server replicating to the target:
   * Write the CA as PEM as the trusted root
   * Write the client cert and client key in `client_format` (`pem` or `der`)
   * config: `test_e2e_mtls_source.json` with the target URL, trusted root and client cert auth
6. Wait for the source replicator to become idle; verify it exists and reports no error.
7. Verify `seed_<server_format>_<client_format>` replicated to the source.
8. Create document `push_<server_format>_<client_format>` on the source; verify it replicates to the target.

## test_edge_to_edge_mtls_rejects_client

**Steps:**
1. Create a CA, a target server certificate and a framework client certificate, and the client identity for `rejected_client`:
   * `no_client_cert`: no client certificate
   * `untrusted_ca`: client certificate signed by a different CA
   * `expired_client_cert`: client certificate signed by the CA that expired a day ago
2. Install the CA and framework client certificate in `~/.cbl_certs` so the test framework can reach the mTLS target.
3. Start the target Edge Server with mTLS, with the server cert, server key and client CA as PEM.
4. Create document `seed_<rejected_client>` on the target `db`.
5. Start the source Edge Server replicating to the target, presenting the `rejected_client` identity.
6. Wait for the source replicator to give up (removed, `Stopped`/`Offline`, or reporting an error).
7. Verify `seed_<rejected_client>` did not replicate to the source.
8. Verify `seed_<rejected_client>` is still on the target.