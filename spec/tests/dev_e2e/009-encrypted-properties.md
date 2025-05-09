# Test Cases

## test_encrypted_push

### Description

Test that an encrypted property does not show up in plaintext on Sync Gateway.

### Steps

1. Reset SG and load `names` dataset
2. Reset local database and load `empty` dataset.
3. Add a document with the following characteristics
    - ID: secret
    - password: "secret_password" (encrypted)
4.  Start a replicator:
        * endpoint: `/names`
        * collections : `_default._default`
        * type: push
        * continuous: false
        * credentials: user1/pass
5. Wait until the replicator is stopped.
6. Check that the document in SG is not in plaintext