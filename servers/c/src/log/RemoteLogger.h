#pragma once

#include "Log.h"
#include <ixwebsocket/IXWebSocket.h>
#include <chrono>
#include <map>
#include <string>
#include <thread>
#include <mutex>
#include <condition_variable>

namespace ts::log {
    class RemoteLogger : public Logger {
    public:
        RemoteLogger(const std::string &url, const std::map<std::string, std::string> &headers);

        ~RemoteLogger() override;

        void connect(std::chrono::seconds timeout);

        void close() override;

        void log(LogLevel level, const char *domain, const char *message) override;

    private:
        ix::WebSocket _webSocket;

        // Connected status:
        std::mutex _mutex;
        std::condition_variable _connectCondition;
        bool _connected{false};

        // Internal method:
        void _close();

        // Callback methods for IXWebSocket
        void onMessage(const ix::WebSocketMessagePtr &msg);
    };
}
