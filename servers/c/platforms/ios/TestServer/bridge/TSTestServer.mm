#import "TSTestServer.h"
#include "TestServer.h"
#include "Files.h"

using namespace ts;

@implementation TSTestServer {
    TestServer *_server;
}

+ (void)initialize {
    TestServer::init();
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
