#include "Zip.h"

#include "Defer.h"
#include <fcntl.h>
#include <filesystem>

#ifndef _MSC_VER

#include <unistd.h>

#define ts_open open
#define _close close
#define _write write
#define O_BINARY 0
#else

#include <io.h>
#include <windows.h>

static int ts_open(const char *filename, int openFlag, [[maybe_unused]] int permission) {
    int fd = -1;
    errno_t err = _sopen_s(&fd, filename, openFlag, _SH_DENYWR, _S_IWRITE);
    if (err != 0) {
        errno = err;
        return -1;
    }

    return fd;
}

#endif

#include <zip.h>

using namespace std;

void zip_support::extractZip(const string &zipFile, const string &dir) {
    int err;
    zip_t *zip = zip_open(zipFile.c_str(), ZIP_RDONLY, &err);
    if (!zip) {
        char errMsg[256];
        zip_error_to_str(errMsg, sizeof(errMsg), err, errno);
        throw std::runtime_error("Cannot open '" + zipFile + "' with error : " + string(errMsg));
    }
    DEFER { zip_close(zip); };

    filesystem::create_directory(dir);

    zip_int64_t numEntries = zip_get_num_entries(zip, 0);
    for (zip_int64_t index = 0; index < numEntries; index++) {
        struct zip_stat stat{};
        if (zip_stat_index(zip, index, 0, &stat) != 0) {
            throw std::runtime_error("Cannot get zip stat at index " + to_string(index));
        }

        if (!(stat.valid & ZIP_STAT_NAME)) {
            continue;
        }

        string extFile = filesystem::path(dir).append(stat.name).string();
        bool isDir = stat.name[strlen(stat.name) - 1] == '/';
        if (isDir) {
            filesystem::create_directory(extFile);
            continue;
        }

        // Open zipped file to read:
        zip_file_t *zipFd = zip_fopen_index(zip, index, 0);
        if (!zipFd) {
            string error = zip_strerror(zip);
            throw std::runtime_error("Cannot open zipped file '" + string(stat.name) + "' with error = " + error);
        }
        DEFER { zip_fclose(zipFd); };

        // Open extracted file to write:
        int fd = ts_open(extFile.c_str(), O_CREAT | O_TRUNC | O_WRONLY | O_BINARY, 0644);
        if (fd < 0) {
            throw std::runtime_error("Cannot open file '" + extFile + "' with error no " + to_string(errno));
        }
        DEFER { _close(fd); };

        char buf[4098];
        zip_int64_t readBytes;
        do {
            readBytes = zip_fread(zipFd, buf, sizeof(buf));
            if (readBytes < 0) {
                string error = zip_strerror(zip);
                throw std::runtime_error("Cannot read zipped file '" + string(stat.name) + "' with error = " + error);
            }

            if (readBytes > 0) {
                auto writtenBytes = _write(fd, buf, (unsigned int) readBytes);
                if (writtenBytes < readBytes) {
                    throw std::runtime_error(
                            "Cannot write file '" + extFile + "' with error no " + to_string(errno));
                }
            }
        } while (readBytes > 0);
    }
}
