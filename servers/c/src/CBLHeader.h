#pragma once

#define STRINGIFY(X) STRINGIFY_(X)
#define STRINGIFY_(X) #X

// Thanks Apple, this sorcery is needed to use frameworks include paths
// (i.e. CouchbaseLite/<path>) work as well as normal include paths
// (i.e. cbl/<path> or fleece/<path>)
#ifdef __APPLE__
#include <TargetConditionals.h>
#if !TARGET_OS_OSX
#define CBL_HEADER(X) STRINGIFY(CouchbaseLite/X)
#define FLEECE_HEADER(X) STRINGIFY(CouchbaseLite/X)
#else
#define CBL_HEADER(X) STRINGIFY(cbl/X)
#define FLEECE_HEADER(X) STRINGIFY(fleece/X)
#endif
#else
#define CBL_HEADER(X) STRINGIFY(cbl/X)
#define FLEECE_HEADER(X) STRINGIFY(fleece/X)
#endif
