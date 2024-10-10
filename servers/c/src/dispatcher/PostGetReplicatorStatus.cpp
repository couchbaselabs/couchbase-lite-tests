#include "Dispatcher+Common.h"

static const string kStatuses[5] = {"STOPPED", "OFFLINE", "CONNECTING", "IDLE", "BUSY"};

int Dispatcher::handlePOSTGetReplicatorStatus(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto id = GetValue<string>(body, "id");
    auto replStatus = session->cblManager()->replicatorStatus(id);
    if (!replStatus) {
        throw RequestError("Replicator '" + id + "' not found");
    }

    json result;
    auto status = replStatus->status;
    result["activity"] = kStatuses[(int) status.activity];

    json progress;
    progress["completed"] = status.progress.complete == 1.0;
    result["progress"] = progress;

    if (status.error.code > 0) {
        result["error"] = CBLException(status.error).json();
    }

    if (replStatus->replicatedDocs) {
        vector<json> docs;
        auto &batches = replStatus->replicatedDocs.value();
        for (auto &batch: batches) {
            for (auto &replDoc: batch) {
                json doc;
                doc["isPush"] = replDoc.isPush;
                doc["collection"] = replDoc.collection;
                doc["documentID"] = replDoc.documentID;
                if (replDoc.error.code > 0) {
                    doc["error"] = CBLException(replDoc.error).json();
                }
                vector<string> flags;
                if (replDoc.flags) {
                    if (replDoc.flags & kCBLDocumentFlagsDeleted) { flags.emplace_back("DELETED"); }
                    if (replDoc.flags & kCBLDocumentFlagsAccessRemoved) {
                        flags.emplace_back("ACCESSREMOVED");
                    }
                }
                doc["flags"] = flags;

                docs.push_back(doc);
            }
        }
        result["documents"] = docs;
    }
    return request.respondWithJSON(result);
}