#pragma once

// FLString from std::string
#define FLS(str) FLStr((str).c_str())

// std::string from FLString
#define STR(str) std::string(static_cast<const char *>((str).buf), (str).size)

// Release CBL object when existing the scope
#define AUTO_RELEASE(o) DEFER { CBL_Release((CBLRefCounted*)(o)); }

// Type-checking for printf-style vararg functions:
#ifdef _MSC_VER
#   define __printflike(A, B)
#else
#   ifndef __printflike
#       define __printflike(fmtarg, firstvararg) __attribute__((__format__(__printf__, fmtarg, firstvararg)))
#   endif
#endif

