# Replication Filters

Here are the list of the predefined replication filters that will be implemented in the test server
and used in the tests.

### documentIDs

The filter that only allows the specified document IDs the to pass.

**name** : `documentIDs`

**params** :

| Key        | Value       |
| :--------- | ----------- |
| documentIDs| `{ <collection-name> : [Array of document-ids>]` |

## deletedDocumentsOnly

The filter that only allows only deleted documents to pass.

**name** : `deletedDocumentsOnly`

**params** : `None`