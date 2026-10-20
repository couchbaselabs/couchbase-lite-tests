// Shared Couchbase Lite <-> Sync Gateway compatibility check, so that no pipeline
// spends hours testing a pair that cannot replicate at all. CBL 4.x syncs with
// version vectors, which Sync Gateway only supports from 4.0: CBL 4.x against
// Sync Gateway 3.x fails every replication. CBL 3.x works with Sync Gateway 3.x
// and 4.x. Source:
// https://docs.couchbase.com/sync-gateway/current/product-notes/compatibility.html
//
// Load it from a Jenkinsfile inside a node/agent context, then call the method on
// the returned object:
//
//     def compat = load 'jenkins/pipelines/shared/cblSgwCompatibility.groovy'
//     def reason = compat.incompatibility(env.CBL_VERSION, env.SGW_VERSION)
//     if (reason) { error reason }

// Major version of "4", "4.1", "4.1.2" or "4.1.2-18".
def majorVersion(String version) {
    return version.trim().tokenize('.-')[0].toInteger()
}

// Returns why `cblVersion` cannot be tested against `sgwVersion`, or null when the
// pair is supported. Both accept a train, a version or a "<version>-<build>".
def incompatibility(String cblVersion, String sgwVersion) {
    if (majorVersion(cblVersion) >= 4 && majorVersion(sgwVersion) < 4) {
        return "CBL ${cblVersion} needs Sync Gateway 4.0 or later, but Sync Gateway is ${sgwVersion}"
    }
    return null
}

return this
