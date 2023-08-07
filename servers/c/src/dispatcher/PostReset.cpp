#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTReset(Request &request) {
    _cblManager->reset();

    json body = request.jsonBody();
    CheckBody(body);
    if (body.contains("datasets")) {
        auto datasets = GetValue<unordered_map<string, vector<string>>>(body, "datasets");
        for (auto &dataset: datasets) {
            auto datasetName = dataset.first;
            auto dbNames = dataset.second;
            if (dbNames.empty()) {
                throw RequestError("dataset '" + datasetName + "' has no database names");
            }
            for (auto &dbName: dbNames) {
                _cblManager->loadDataset(datasetName, dbName);
            }
        }
    }
    return request.respondWithOK();
}