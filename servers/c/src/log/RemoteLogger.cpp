#include "RemoteLogger.h"

#include <sstream>
#include <ixwebsocket/IXNetSystem.h>

using namespace std;

namespace ts::log {
    RemoteLogger::RemoteLogger(const std::string &url,
                               const std::map<std::string, std::string> &headers) {
        ix::initNetSystem(); // For Windows

        _webSocket.setUrl("ws://" + url + "/openLogStream");
        _webSocket.disableAutomaticReconnection();
        _webSocket.setOnMessageCallback([this](const ix::WebSocketMessagePtr &msg) {
            onMessage(msg);
        });

        ix::WebSocketHttpHeaders extraHeaders;
        for (const auto &header: headers) {
            extraHeaders[header.first] = header.second;
        }
        _webSocket.setExtraHeaders(extraHeaders);
    }

    RemoteLogger::~RemoteLogger() {
        _close();
        ix::uninitNetSystem(); // For Windows
    }

    void RemoteLogger::connect(std::chrono::seconds timeout) {
        unique_lock<mutex> lock(_mutex);
        if (_connected) {
            return;
        }

        _webSocket.start();

        auto connected = _connectCondition.wait_for(lock, timeout, [this]() {
            return _connected;
        });

        if (!connected) {
            _close();
        }
    }

    void RemoteLogger::close() {
        _close();
    }

    void RemoteLogger::_close() {
        _webSocket.stop(); // Synchronous
    }

    void RemoteLogger::log(LogLevel level, const char *domain, const char *message) {
        {
            lock_guard<mutex> lock(_mutex);
            if (!_connected) {
                return;
            }
        }

        std::stringstream ss;
        ss << "[" << logLevelNames[(int) level] << "] " << domain << ": " << message;
        _webSocket.sendText(ss.str());
    }

    void RemoteLogger::onMessage(const ix::WebSocketMessagePtr &msg) {
        if (msg->type == ix::WebSocketMessageType::Open ||
            msg->type == ix::WebSocketMessageType::Close ||
            msg->type == ix::WebSocketMessageType::Error) {
            lock_guard<mutex> lock(_mutex);
            _connected = msg->type == ix::WebSocketMessageType::Open;
            _connectCondition.notify_all();
        }
    }
}
