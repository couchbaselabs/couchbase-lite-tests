// Shared ProGet build lookups for the trigger pipelines (jenkins/pipelines/main/*) and any
// pipeline that turns a version, train or "<version>-<build>" into a concrete build.
//
// Load it from a Jenkinsfile inside a node/agent context (so sh is available), then call
// the methods on the returned object:
//
//     def proget = load 'jenkins/pipelines/shared/resolveProgetVersion.groovy'
//     def builds = load 'jenkins/pipelines/shared/progetBuilds.groovy'
//     def info = builds.resolveVersionBuild(proget, 'sync-gateway', '4.2', 'SGW_VERSION', true)
//     // info == [version: "4.2.0", build: "9"], or null when the train has no build yet
//
// Overloads are avoided for the same reason as in resolveProgetVersion.groovy: the CPS
// transform does not reliably handle the bridge methods default arguments generate.

// Look up a version's build number via ProGet get_version. Returns "" when the
// version has no published build yet (404 / non-JSON body) rather than throwing.
def getBuildNumber(String product, String version) {
    def url = "http://proget.build.couchbase.com:8080/api/get_version?product=${product}&version=${version}"
    return sh(
        script: "curl -s --max-time 30 '${url}' | python3 -c 'import json,sys; s=sys.stdin.read().strip(); print(json.loads(s).get(\"BuildNumber\",\"\") if s.startswith(\"{\") else \"\")'",
        returnStdout: true
    ).trim()
}

// Resolves `param` (blank, a train, a version or "<version>-<build>") to
// [version: ..., build: ...]. A fully-qualified "<version>-<build>" is used as-is;
// otherwise the version comes from resolveProgetVersion and the build from
// getBuildNumber. Returns null when that version has no published build yet (a normal
// new-train state right after a manifest version bump, since the previous patch is
// frozen and can no longer be built) so the caller can skip it quietly; genuine
// failures still throw.
//
// `includePrerelease` is true for the product under test (a nightly must pick up the
// newest build) and false for a client held at GA as a fixed control.
def resolveVersionBuild(proget, String product, String param, String label, boolean includePrerelease) {
    def version = proget.resolveProgetVersion(product, param, label, includePrerelease)
    def buildNo
    if (version.contains('-')) {
        def parts = version.split('-', 2)
        version = parts[0]
        buildNo = parts[1]
    } else {
        buildNo = getBuildNumber(product, version)
    }
    if (!buildNo) { return null }  // no published build for this train yet
    return [version: version, build: buildNo]
}

// Fetch the list of currently-supported (non-EOL) trains for a product, e.g.
// get_trains?product=couchbase-lite-ios -> ["3.2","3.3","4.0","3.4","4.1","4.2"].
def fetchTrains(String product) {
    def url = "http://proget.build.couchbase.com:8080/api/get_trains?product=${product}"
    def raw = sh(
        script: "curl -sf --max-time 30 '${url}' | python3 -c 'import json,sys; print(\"\\n\".join(json.load(sys.stdin)))'",
        returnStdout: true
    ).trim()
    return raw ? raw.tokenize() : []
}

return this
