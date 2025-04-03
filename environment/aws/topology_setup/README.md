# Topology AWS setup

This is not something that gets deployed to a single node, but rather a concept that will allow creation and setup of multiple needed nodes.  It is a recipe for how many nodes to create, what to install onto them, and how to make them aware or unaware of each other.

## Topology File

### AWS

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
],
"logslurp": true
```

This recipe is saying that we need one Couchbase Server cluster, which has one server node inside of it.  In addition, we also need a Sync Gateway node that is backed by the cluster at index 0 (the only cluster in this case).  If for some reason you need more nodes in the cluster, then raise the `server_count` as you like.  And on the last line, it is indicated that logslurp should also be deployed (this one only requires either one or zero instances, and so it is a boolean)

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

### Test Server

In addition to AWS resources, this system can also build / download, install, run, and stop test server instances.  Here is what an example of that looks like:

```json
{
    "test-servers": [
        {
            "platform": "dotnet_ios",
            "location": "123456",
            "cbl_version": "3.2.2-24",
            "dataset_version": "3.2"
        }
    ]
}
```

The above indicates that one test server is desired.  It is the .NET iOS Test Server, and it should be built using CBL version 3.2.2-24 and dataset version 3.2.  After that, it should be deployed to a connected iOS device with the serial number "123456" (replace with an actual serial number).

If downloading a prebuilt test server instead, simply add `{"download": true}` to the above:

```json
{
    "test-servers": [
        {
            "platform": "dotnet_ios",
            "location": "123456",
            "cbl_version": "3.2.2-24",
            "dataset_version": "3.2",
            "download": true
        }
    ]
}
```

There are some limitations on the possible values of `location`.  They are expected to be as follows:

| Platform | OS | location |
| -- | -- | -- |
| Java | Android | device serial |
| | Windows | localhost |
| | macOS | localhost |
| | Linux | localhost |
| .NET | Android | device serial |
| | iOS | device serial |
| | Windows | localhost |
| | macOS | localhost |
| Swift | iOS | device serial |
| C | Android | device serial |
| | iOS | device serial |
| | Windows | localhost |
| | macOS | localhost |
| | Linux x86_64 | localhost |
| | Linux armhf | *unsupported* |
| | Linux arm64 | *unsupported* |