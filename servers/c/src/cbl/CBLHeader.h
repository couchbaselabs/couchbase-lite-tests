#pragma once

#define STRINGIFY(X) STRINGIFY_(X)
#define STRINGIFY_(X) #X

#ifdef __APPLE__

#include <TargetConditionals.h>
// Note : Not using TARGET_OS_OSX here because it doesn't work with CLion editor when the
//        other headers include this header for some reason but works fine during build.
#if !TARGET_OS_IPHONE && !TARGET_OS_SIMULATOR
#define CBL_HEADER(X) STRINGIFY(cbl/X)
#define FLEECE_HEADER(X) STRINGIFY(fleece/X)
#else
#define CBL_HEADER(X) STRINGIFY(CouchbaseLite/X)
#define FLEECE_HEADER(X) STRINGIFY(CouchbaseLite/X)
#endif

#else
#define CBL_HEADER(X) STRINGIFY(cbl/X)
#define FLEECE_HEADER(X) STRINGIFY(fleece/X)
#endif
