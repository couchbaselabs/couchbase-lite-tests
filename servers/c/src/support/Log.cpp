#include "Log.h"
#include "date.h"

// cbl
#include "CBLManager.h"

// lib
#include <chrono>
#include <stdexcept>
#include <iostream>

#ifdef __ANDROID__
#include <android/log.h>
#endif

#ifdef _MSC_VER
#include "asprintf.h"
#endif

using namespace ts::cbl;

using namespace date;
using namespace std;

namespace ts::support {

    static const char *const kTestServerLogDomainName = "TS";

    static const char *const kCBLLogDomainName[] = {"DB", "Query", "Sync", "WS"};

    static const char *const kLogLevelNames[] = {"debug", "verbose", "info", "warning", "error", "none"};

    struct Timestamp {
        time_t secs;
        unsigned microsecs;
    };

    static Timestamp now() {
        using namespace chrono;
        auto now = time_point_cast<microseconds>(system_clock::now());
        auto count = now.time_since_epoch().count();
        time_t secs = (time_t) count / 1000000;
        unsigned microsecs = count % 1000000;
        return {secs, microsecs};
    }

    static struct tm FromTimestamp(std::chrono::seconds timestamp) {
        local_seconds tp{timestamp};
        auto dp = floor<days>(tp);
        year_month_day ymd{dp};
        auto hhmmss = make_time(tp - dp);

        struct tm local_time{};
        local_time.tm_sec = (int) hhmmss.seconds().count();
        local_time.tm_min = (int) hhmmss.minutes().count();
        local_time.tm_hour = (int) hhmmss.hours().count();
        local_time.tm_mday = (int) static_cast<unsigned>(ymd.day());
        local_time.tm_mon = (int) static_cast<unsigned>(ymd.month()) - 1;
        local_time.tm_year = static_cast<int>(ymd.year()) - 1900;
        local_time.tm_isdst = -1;

        return local_time;
    }

    static std::chrono::seconds GetLocalTZOffset(struct tm *localtime) {
        // This method is annoyingly delicate, and warrants lots of explanation

        // First, call tzset so that the needed information is populated
        // by the C runtime
#if !defined(_MSC_VER) || WINAPI_FAMILY_PARTITION(WINAPI_PARTITION_DESKTOP)
        // Let's hope this works on UWP since Microsoft has removed the
        // tzset and _tzset functions from UWP
        static std::once_flag once;
        std::call_once(once, [] {
#ifdef _MSC_VER
            _tzset();
#else
            tzset();
#endif
        });
#endif

        // Find the system time zone's offset from UTC
        // Windows -> _get_timezone
        // Others -> global timezone variable
        //      https://linux.die.net/man/3/tzset (System V-like / XSI)
        //      http://www.unix.org/version3/apis/t_9.html (Unix v3)
        //
        // NOTE: These values are the opposite of what you would expect, being defined
        // as seconds WEST of GMT (so UTC-8 would be 28,800, not -28,800)
#ifdef WIN32
        long s;
        if (_get_timezone(&s) != 0) {
            throw runtime_error("Unable to query local system time zone");
        }
        auto offset = seconds(-s);
#elif defined(__DARWIN_UNIX03) || defined(__ANDROID__) || defined(_XOPEN_SOURCE) || defined(_SVID_SOURCE)
        auto offset = std::chrono::seconds(-timezone);
#else
#error Unimplemented GetLocalTZOffset
#endif

        // Apply the timezone offset first to get the proper time
        // in the current timezone (no-op if local time was passed)
        localtime->tm_sec -= (int) offset.count();

        // In order to consider DST, mktime needs to be called.
        // However, this has the caveat that it will never be
        // clear if the "before" or "after" DST is desired in the case
        // of a rollback of clocks in which an hour is repeated.  Moral
        // of the story:  USE TIME ZONES IN YOUR DATE STRINGS!
        if (mktime(localtime) != -1) {
            offset += std::chrono::hours(localtime->tm_isdst);
        }

        return offset;
    }

    static void writeTimestamp(Timestamp t, ostream &out) {
        local_time<std::chrono::microseconds> tp{std::chrono::seconds(t.secs) + std::chrono::microseconds(t.microsecs)};
        struct tm tmpTime = FromTimestamp(duration_cast<std::chrono::seconds>(tp.time_since_epoch()));
        tp -= GetLocalTZOffset(&tmpTime);
        out << format("%T| ", tp);
    }

    static void writeHeader(const string &levelName, const string &domainName, ostream &out) {
        if (!levelName.empty()) {
            if (!domainName.empty())
                out << '[' << domainName << "] ";
            out << levelName << ": ";
        } else {
            if (!domainName.empty())
                out << '[' << domainName << "]: ";
        }
    }

    static void vlog(CBLLogLevel level, const char *domain, const char *format, va_list args) {
        char *message = nullptr;
        if (vasprintf(&message, format, args) < 0) {
            throw bad_alloc();
        }

#ifdef __ANDROID__
        string tag("CouchbaseLite/TS");
        if (domain) {
            tag += " [" + string(domain) + "]";
        }
        static const int androidLevels[5] = {ANDROID_LOG_DEBUG, ANDROID_LOG_INFO,
                                             ANDROID_LOG_INFO, ANDROID_LOG_WARN,
                                             ANDROID_LOG_ERROR};
        __android_log_write(androidLevels[(int) level], tag.c_str(), message);
#else

        auto levelName = kLogLevelNames[(int) level];
        ostream &os = level < kCBLLogWarning ? cout : cerr;
        writeTimestamp(now(), os);
        writeHeader(levelName, domain, os);
        os << message << endl;
#endif
    }

    static void mlog(CBLLogLevel level, CBLLogDomain domain, const char *format, ...) {
        va_list args;
        va_start(args, format);
        vlog(level, kCBLLogDomainName[domain], format, args);
        va_end(args);
    }

    static logger::LogLevel sLogLevel = logger::LogLevel::none;

    void logger::init(LogLevel level) {
        sLogLevel = level;
        CBLLog_SetCallbackLevel((CBLLogLevel) level);
        CBLLog_SetCallback([](CBLLogDomain domain, CBLLogLevel level, FLString msg) {
            mlog(level, domain, "%.*s", msg.size, msg.buf);
        });
    }

    void logger::log(LogLevel level, const char *format, ...) {
        if (level >= sLogLevel) {
            va_list args;
            va_start(args, format);
            vlog((CBLLogLevel) level, kTestServerLogDomainName, format, args);
            va_end(args);
        }
    }
}
