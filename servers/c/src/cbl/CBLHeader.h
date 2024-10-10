#pragma once

#define STRINGIFY(X) STRINGIFY_(X)
#define STRINGIFY_(X) #X

#ifdef __APPLE__

#include <TargetConditionals.h>

#ifdef TARGET_OS_OSX
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
