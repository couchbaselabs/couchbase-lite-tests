# Topology AWS setup

This is not something that gets deployed to a single node, but rather a concept that will allow creation and setup of multiple needed nodes.  It is a recipe for how many nodes to create, what to install onto them, and how to make them aware or unaware of each other.

## Topology File

The recipe format is a JSON file that has two simple entries.  Let's take a look at the [Default Topology](./default_topology.json)

```json
"clusters": [
    {
        "server_count": 1
    }
],
"sync_gateways": [
    {
        "cluster": 0
    }
]
```

This recipe is saying that we need one Couchbase Server cluster, which has one server node inside of it.  In addition, we also need a Sync Gateway node that is backed by the cluster at index 0 (the only cluster in this case).  If for some reason you need more nodes in the cluster, then raise the `server_count` as you like.

Now let's say you want two sync gateways backed by two independent clusters.  You could modify the file as follows:

```json
"clusters": [
    {
        "server_count": 1
    },
    {
        "server_count": 1
    }
],
"sync_gateways": [
    {
        "cluster": 0
    },
    {
        "cluster": 1
    }
]
```

As you can see, it is easy to create the topologies you need.  You could have both Sync Gateways pointing to the same cluster, or you could raise the server count in each cluster independently.