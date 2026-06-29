// Shared helper to resolve a partial product version (e.g. "4") to a concrete
// released version via ProGet. A fully-qualified version (>= 3 dot-separated
// components, e.g. "4.1.0" or "4.1.0-18") is returned unchanged.
//
// Load it from a Jenkinsfile inside a node/agent context (so sh/powershell are
// available), then call the method on the returned object:
//
//     def proget = load 'jenkins/pipelines/shared/resolveProgetVersion.groovy'
//     env.CBL_VERSION = proget.resolveProgetVersion('couchbase-lite-c', params.CBL_VERSION, 'CBL_VERSION')
def resolveProgetVersion(String product, String version, String label) {
    if (version.tokenize('.').size() >= 3) {
        echo "${label} already fully qualified: ${version}"
        return version
    }
    def url = "http://proget.build.couchbase.com:8080/api/latest_release?product=${product}&version=${version}&prerelease=true"
    echo "Resolving ${label}: ${url}"
    def resolved
    if (isUnix()) {
        resolved = sh(
            script: "curl -sf '${url}' | python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"version\",\"\"))'",
            returnStdout: true
        ).trim()
    } else {
        resolved = powershell(script: """
            try { (Invoke-RestMethod '${url}').version }
            catch { Write-Error "ProGet request failed for ${label}: ${'$'}_"; exit 1 }
        """.stripIndent(), returnStdout: true).trim()
    }
    if (!resolved || resolved == 'null') { error "Could not resolve ${label} from '${version}' (url: ${url})" }
    echo "Resolved ${label}: ${resolved}"
    return resolved
}

return this
