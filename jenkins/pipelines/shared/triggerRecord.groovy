// Shared record of which builds a trigger pipeline (jenkins/pipelines/main/*) has already
// started a test run for, so a daily run only tests builds it has not seen.
//
// A record is a { "<version>": "<build>" } map, kept in
// ~/.jenkins_build_info/<job name>/<name>.json on the agent the job runs on, so a trigger
// job must stay pinned to one agent and keep its name for its record to carry over.
//
// Load it from a Jenkinsfile inside a node/agent context, then call the methods on the
// returned object:
//
//     def triggers = load 'jenkins/pipelines/shared/triggerRecord.groovy'
//     def record = triggers.readRecord('sgw')
//     if (!force && triggers.alreadyTriggered(record, '4.2.0', '9')) { ... skip ... }
//     record['4.2.0'] = '9'
//     triggers.saveRecord('sgw', record)

def recordFile(String name) {
    return "${env.HOME}/.jenkins_build_info/${env.JOB_NAME}/${name}.json"
}

// Returns the record, or an empty map when there is none yet or it cannot be read.
def readRecord(String name) {
    def file = recordFile(name)
    echo "Build Info File: ${file}"
    if (!fileExists(file)) {
        return [:]
    }
    try {
        return readJSON(file: file, returnPojo: true)
    } catch (Exception e) {
        echo "WARN : Error when reading ${name}.json : ${e}"
        return [:]
    }
}

def alreadyTriggered(Map record, String version, String build) {
    return record[version] == build
}

def saveRecord(String name, Map record) {
    try {
        writeJSON file: recordFile(name), json: record
    } catch (Exception e) {
        error "Cannot save ${name}.json with error: ${e}"
    }
}

return this
