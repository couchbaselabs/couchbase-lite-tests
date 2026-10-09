// Shared helper to resolve a partial product version (e.g. "4") to a concrete
// published version via ProGet. A fully-qualified version (>= 3 dot-separated
// components, e.g. "4.1.0" or "4.1.0-18") is returned unchanged.
// Pass an empty/blank version to resolve the newest version with no version filter
// applied.
//
// `includePrerelease` selects which feed is consulted:
//   true  (default) - prereleases included, so a blank version resolves the current
//                     mainline (master) build. Use for the product under test.
//   false           - GA only, matching `resolve_latest_version` in
//                     environment/aws/common/versions.py. Use for a client that is
//                     meant to be a fixed control, not the thing under test.
//
// Load it from a Jenkinsfile inside a node/agent context (so sh/powershell are
// available), then call the method on the returned object:
//
//     def proget = load 'jenkins/pipelines/shared/resolveProgetVersion.groovy'
//     env.CBL_VERSION = proget.resolveProgetVersion('couchbase-lite-c', params.CBL_VERSION, 'CBL_VERSION')
//
// Overloads are written out explicitly rather than using Groovy default arguments,
// because the CPS transform does not reliably transform the synthetic bridge methods
// that default arguments generate.
def resolveProgetVersion(String product, String version, String label) {
    return resolveProgetVersion(product, version, label, true)
}

def resolveProgetVersion(String product, String version, String label, boolean includePrerelease) {
    version = version?.trim()

    if (version && version.tokenize('.').size() >= 3) {
        echo "${label} already fully qualified: ${version}"
        return version
    }
    def url = "http://proget.build.couchbase.com:8080/api/latest_release?product=${java.net.URLEncoder.encode(product, 'UTF-8')}"
    // Omitting the flag entirely (rather than passing false) is what restricts ProGet
    // to GA builds; see environment/aws/common/versions.py.
    if (includePrerelease) {
        url += "&prerelease=true"
    }
    if (version) {
        url += "&version=${java.net.URLEncoder.encode(version, 'UTF-8')}"
    }
    echo "Resolving ${label} (${includePrerelease ? 'prerelease' : 'GA only'}): ${url}"
    def resolved
    if (isUnix()) {
        resolved = sh(
            script: "curl -sf --max-time 30 '${url}' | python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"version\",\"\"))'",
            returnStdout: true
        ).trim()
    } else {
        resolved = powershell(script: """
            try { (Invoke-RestMethod -TimeoutSec 30 '${url}').version }
            catch { Write-Error "ProGet request failed for ${label}: ${'$'}_"; exit 1 }
        """.stripIndent(), returnStdout: true).trim()
    }
    if (!resolved || resolved == 'null') { error "Could not resolve ${label} from '${version}' (url: ${url})" }
    echo "Resolved ${label}: ${resolved}"
    return resolved
}

return this
