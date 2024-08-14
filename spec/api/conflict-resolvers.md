# Conflict Resolvers

Here are the list of the predefined conflict resolvers that will be implemented in the test server
and used in the tests.

### local-wins

Universally returns the local document

**name** : `local-wins`

**params** : `None`

### remote-wins

Universally returns the remote document

**name** : `remote-wins`

**params** : `None`

### delete

Universally returns null (i.e. deletion)

**name** : `delete`

**params** : `None`

### merge

Performs a merge of the specified property by changing it to an array containing both values.
For simplicity, restrict to top level keys.

**name** : `merge`

**params** :

| Key        | Value       |
| :--------- | ----------- |
| property| `<top level key>` |

