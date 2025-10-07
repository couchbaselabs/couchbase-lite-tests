#pragma once

#include <string>

namespace ts::support {
    class FileDownloader {
    public:
        static void download(const std::string& url, const std::string& destinationPath);
    };
}