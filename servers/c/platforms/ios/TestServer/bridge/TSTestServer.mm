#import "TSTestServer.h"
#include "TestServer.h"
#include "Files.h"

using namespace ts;

@implementation TSTestServer {
    TestServer *_server;
}

+ (instancetype)shared {
    static TSTestServer *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        TestServer::init();
        instance = [[self alloc] init];
    });
    return instance;
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
