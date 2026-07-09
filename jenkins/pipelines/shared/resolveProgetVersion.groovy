// Shared helper to resolve a partial product version (e.g. "4") to a concrete
// published version via ProGet (including prereleases when available). A fully-qualified
// version (>= 3 dot-separated components, e.g. "4.1.0" or "4.1.0-18") is returned unchanged.
// Pass an empty/blank version to resolve the current mainline (master) version instead,
// i.e. the newest prerelease with no version filter applied.
//
// Load it from a Jenkinsfile inside a node/agent context (so sh/powershell are
// available), then call the method on the returned object:
//
//     def proget = load 'jenkins/pipelines/shared/resolveProgetVersion.groovy'
//     env.CBL_VERSION = proget.resolveProgetVersion('couchbase-lite-c', params.CBL_VERSION, 'CBL_VERSION')
def resolveProgetVersion(String product, String version, String label) {
    version = version?.trim()

    if (version && version.tokenize('.').size() >= 3) {
        echo "${label} already fully qualified: ${version}"
        return version
    }
    def url = "http://proget.build.couchbase.com:8080/api/latest_release?product=${java.net.URLEncoder.encode(product, 'UTF-8')}&prerelease=true"
    if (version) {
        url += "&version=${java.net.URLEncoder.encode(version, 'UTF-8')}"
    }
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
