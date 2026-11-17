// Shared record of which builds a trigger pipeline (jenkins/pipelines/main/*) has already
// started a test run for, so a daily run only tests builds it has not seen.
//
// The record lives in Alembic's latest_tested API (http://proget.build.couchbase.com:8080,
// see /swagger): one build number per product + X.Y.Z version, shared by every agent and
// every trigger job. Alembic normalizes alternate product names (sync-gateway is stored
// as sync_gateway), so pass the same ProGet product name used for the lookup.
//
// Load it from a Jenkinsfile inside a node/agent context (so sh is available), then call
// the methods on the returned object:
//
//     def triggers = load 'jenkins/pipelines/shared/triggerRecord.groovy'
//     if (!force && triggers.alreadyTriggered('sync-gateway', '4.2.0', '9')) { ... skip ... }
//     if (!triggers.record('sync-gateway', '4.2.0', '9')) { ... warn ... }

// A method, not a top-level def: script-level locals are not visible inside methods.
def baseUrl() {
    return 'http://proget.build.couchbase.com:8080/api/latest_tested'
}

// Returns the last recorded build number of product+version as a string, or '' when none
// is recorded yet (404) or the lookup failed (a failed lookup only risks a re-trigger).
def lastTestedBuild(String product, String version) {
    def out = sh(
        script: "curl -s --max-time 30 -w '\\n%{http_code}' -G '${baseUrl()}' --data-urlencode 'product=${product}' --data-urlencode 'version=${version}'",
        returnStdout: true
    ).trim()
    def lines = out.split('\n')
    def status = lines[-1].trim()
    if (status == '404') {
        return ''
    }
    if (status != '200') {
        echo "WARN: latest_tested lookup for ${product} ${version} returned HTTP ${status}"
        return ''
    }
    try {
        return readJSON(text: lines[0..-2].join('\n'), returnPojo: true).build.toString()
    } catch (Exception e) {
        echo "WARN: could not parse latest_tested for ${product} ${version}: ${e}"
        return ''
    }
}

def alreadyTriggered(String product, String version, String build) {
    return lastTestedBuild(product, version) == build
}

// Records build as the latest tested for product+version, replacing any earlier value.
// Returns false (after a warning) when Alembic did not accept it.
def record(String product, String version, String build) {
    def body = groovy.json.JsonOutput.toJson([product: product, version: version, build: build.toInteger()])
    def status = sh(
        script: "curl -s --max-time 30 -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '${body}' '${baseUrl()}'",
        returnStdout: true
    ).trim()
    if (status != '200') {
        echo "WARN: could not record ${product} ${version}-${build} as tested (HTTP ${status})"
        return false
    }
    return true
}

return this
