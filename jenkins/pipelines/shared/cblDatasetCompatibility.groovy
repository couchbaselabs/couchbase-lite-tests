// Shared Couchbase Lite <-> test dataset compatibility. A dataset is a set of prebuilt
// databases made with one Couchbase Lite version, and Couchbase Lite cannot open a database
// made by a later major version: CBL 3.x cannot use the 4.0 dataset. CBL 4.x can use either,
// since it upgrades a 3.2 database when it opens it.
//
// Load it from a Jenkinsfile inside a node/agent context, then call the method on
// the returned object:
//
//     def datasets = load 'jenkins/pipelines/shared/cblDatasetCompatibility.groovy'
//     def reason = datasets.incompatibility(env.CBL_RESOLVED, params.TS_DATASET_VERSION)
//     if (reason) { error reason }

// Major version of "4", "4.1", "4.1.2" or "4.1.2-18".
def majorVersion(String version) {
    return version.trim().tokenize('.-')[0].toInteger()
}

// The dataset a run of `cblVersion` uses unless told otherwise: the dataset of its own major
// version, so 3.2 for CBL 3.x and 4.0 for 4.x and later.
def datasetFor(String cblVersion) {
    return majorVersion(cblVersion) >= 4 ? '4.0' : '3.2'
}

// Returns why `cblVersion` cannot use dataset `dataset` ("3.2" or "4.0"), or null when it can.
def incompatibility(String cblVersion, String dataset) {
    if (majorVersion(dataset) > majorVersion(cblVersion)) {
        return "CBL ${cblVersion} cannot open the ${dataset} dataset: it needs CBL ${majorVersion(dataset)}.x or later"
    }
    return null
}

return this
