// The versions a functional pipeline runs with. Each pipeline has one product under test, whose version
// parameter is required. The versions of the other products (Couchbase Lite, Sync Gateway and Edge Server)
// are optional, and a blank one means their latest release.
//
// Every version parameter takes the same forms: "4" or "4.1" (a train), "4.1.0" (that version, its newest
// build) or "4.1.0-18" (that build). A train resolves to its newest version: prereleases included for the
// product under test, releases only for the others. To run another product's prerelease, give its version.
// One exception to "blank is the latest release": with Sync Gateway under test, a blank Couchbase Lite version
// is the latest release of the Sync Gateway's major version (Sync Gateway 3.2.4 gets the latest CBL 3.x).
//
// Load it from a Jenkinsfile inside a node/agent context, then call resolve() with the product under test
// ('cbl', 'sgw' or 'es'), the ProGet product of the pipeline's Couchbase Lite, and the pipeline's params:
//
//     def versions = load 'jenkins/pipelines/shared/productVersions.groovy'
//     versions.resolve('cbl', 'couchbase-lite-c', params)
//
// It sets, as environment variables of the build:
//   CBL_RESOLVED, SGW_RESOLVED, ES_RESOLVED  each product's version, fully qualified ("4.1.0" or "4.1.0-18")
//   CBL_PREBUILD_VERSION, CBL_PREBUILD_BUILD  CBL_RESOLVED split for the prebuild-test-server job (blank build:
//                                            its newest build)
// and fails the build when the version under test is blank, a version does not resolve, the Couchbase Lite
// and Sync Gateway versions cannot replicate (see cblSgwCompatibility.groovy), or the pipeline has a
// TS_DATASET_VERSION parameter that names a dataset its Couchbase Lite cannot open (see
// cblDatasetCompatibility.groovy).

def resolve(String underTest, String cblProduct, Map p) {
    def products = [
        cbl: [product: cblProduct, param: 'CBL_VERSION'],
        sgw: [product: 'sync-gateway', param: 'SGW_VERSION'],
        es : [product: 'couchbase-edge-server', param: 'ES_VERSION'],
    ]
    if (!products.containsKey(underTest)) {
        error "productVersions.resolve: unknown product under test '${underTest}' (cbl, sgw or es)"
    }

    def proget = load 'jenkins/pipelines/shared/resolveProgetVersion.groovy'
    def compat = load 'jenkins/pipelines/shared/cblSgwCompatibility.groovy'
    def resolved = [:]
    // Sync Gateway first: with Sync Gateway under test, a blank Couchbase Lite version follows its major version.
    for (key in ['sgw', 'cbl', 'es']) {
        def spec = products[key]
        def given = (p[spec.param] ?: '').trim()
        if (key == underTest && !given) {
            error "${spec.param} is required: it is the version of the product under test"
        }
        if (key == 'cbl' && underTest == 'sgw' && !given) {
            // The latest Couchbase Lite release of the Sync Gateway's major version: 3.x for Sync Gateway 3.x
            // (Couchbase Lite 4.x cannot replicate with it), 4.x for Sync Gateway 4.x.
            given = "${compat.majorVersion(resolved.sgw)}"
        }
        // Only the product under test resolves a train to a prerelease; a blank version is the latest release.
        resolved[key] = proget.resolveProgetVersion(spec.product, given, spec.param, key == underTest)
    }

    def reason = compat.incompatibility(resolved.cbl, resolved.sgw)
    if (reason) { error reason }
    if (p.TS_DATASET_VERSION) {
        def datasets = load 'jenkins/pipelines/shared/cblDatasetCompatibility.groovy'
        reason = datasets.incompatibility(resolved.cbl, p.TS_DATASET_VERSION)
        if (reason) { error reason }
    }

    env.CBL_RESOLVED = resolved.cbl
    env.SGW_RESOLVED = resolved.sgw
    env.ES_RESOLVED = resolved.es
    def cblParts = resolved.cbl.tokenize('-')
    env.CBL_PREBUILD_VERSION = cblParts[0]
    env.CBL_PREBUILD_BUILD = cblParts.size() > 1 ? cblParts[1] : ''
    echo "Versions (${underTest} under test): CBL ${env.CBL_RESOLVED}, SGW ${env.SGW_RESOLVED}, ES ${env.ES_RESOLVED}"
}

return this
