#include "CollectionSpec.h"

#include "support/CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include "support/Define.h"

CollectionSpec::CollectionSpec(const CBLCollection *collection) {
    _scope = STR(CBLScope_Name(CBLCollection_Scope(collection)));
    _name = STR(CBLCollection_Name(collection));
    _fullName = _scope + "." + _name;
}