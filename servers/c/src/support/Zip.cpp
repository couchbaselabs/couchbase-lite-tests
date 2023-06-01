#include "Zip.h"

#include "Defer.h"
#include <fcntl.h>
#include <filesystem>

#ifndef _MSC_VER

#include <sys/stat.h>
#include <unistd.h>

#define _open open
#define _close close
#define _write write
#else

#include <io.h>
#include <windows.h>

#endif

#include <zip.h>

using namespace std;

void createDirectory(const string &dir) {
#ifdef WIN32
    bool success = _mkdir(dir.c_str()) == 0 || errno == EEXIST;
#else
    bool success = mkdir(dir.c_str(), 0744) == 0 || errno == EEXIST;
#endif
    if (!success) {
        throw std::runtime_error("Cannot create directory '" + dir + "', with error no " + to_string(errno));
    }
}

void support::extractZip(const string &zipFile, const string &dir) {
    int err;
    zip_t *zip = zip_open(zipFile.c_str(), ZIP_RDONLY, &err);
    if (!zip) {
        char errMesg[256];
        zip_error_to_str(errMesg, sizeof(errMesg), err, errno);
        throw std::runtime_error("Cannot open '" + zipFile + "' with error : " + string(errMesg));
    }
    DEFER { zip_close(zip); };

    createDirectory(dir);

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
            createDirectory(extFile);
            continue;
        }

        zip_file_t *zipFile = zip_fopen_index(zip, index, 0);
        if (!zipFile) {
            string error = zip_strerror(zip);
            throw std::runtime_error("Cannot open zipped file '" + string(stat.name) + "' with error = " + error);
        }
        DEFER { zip_fclose(zipFile); };

        /* try to open the file in the filesystem for writing */
        int fd = _open(extFile.c_str(), O_CREAT | O_TRUNC | O_WRONLY, 0644);
        if (fd < 0) {
            throw std::runtime_error("Cannot open file '" + extFile + "' with error no " + to_string(errno));
        }
        DEFER { _close(fd); };

        char buf[4098];
        zip_int64_t readBytes = 0;
        do {
            readBytes = zip_fread(zipFile, buf, sizeof(buf));
            if (readBytes < 0) {
                string error = zip_strerror(zip);
                throw std::runtime_error("Cannot read zipped file '" + string(stat.name) + "' with error = " + error);
            }

            if (readBytes > 0) {
                auto writtenBytes = _write(fd, buf, readBytes);
                if (writtenBytes < readBytes) {
                    throw std::runtime_error(
                            "Cannot write file '" + extFile + "' with error no " + to_string(errno));
                }
            }
        } while (readBytes > 0);
    }
}
