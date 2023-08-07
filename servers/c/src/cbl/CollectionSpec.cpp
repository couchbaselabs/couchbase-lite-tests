#include "CollectionSpec.h"

// support
#include "CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include "Define.h"

CollectionSpec::CollectionSpec(const CBLCollection *collection) {
    _scope = STR(CBLScope_Name(CBLCollection_Scope(collection)));
    _name = STR(CBLCollection_Name(collection));
    _fullName = _scope + "." + _name;
}

CollectionSpec::CollectionSpec(const std::string &scope, const std::string &name) {
    _scope = scope;
    _name = name;
    _fullName = scope + "." + name;
}