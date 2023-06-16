#import "CBLTestServer.h"
#include "TestServer.h"
#include "Files.h"

@implementation CBLTestServer {
    TestServer *_server;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        TestServer::Context context = {
            ts_support::files::tempDir("CBL-C-TestServer", true),
            ts_support::files::assetDir()
        };
        _server = new TestServer(context);
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
