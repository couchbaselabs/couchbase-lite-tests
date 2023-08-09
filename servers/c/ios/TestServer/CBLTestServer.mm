#import "CBLTestServer.h"
#include "TestServer.h"
#include "Files.h"

using namespace ts;

@implementation CBLTestServer {
    TestServer *_server;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _server = new TestServer();
    }
    return self;
}

- (void)start {
    _server->start();
}

- (void)stop {
    _server->stop();
}

@end
