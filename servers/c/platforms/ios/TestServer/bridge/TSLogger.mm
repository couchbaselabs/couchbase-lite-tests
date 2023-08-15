#import "TSLogger.h"
#include "Log.h"

using namespace ts::support;
using namespace ts::support::logger;

@implementation TSLogger

+ (void)info: (NSString*)message {
    const char* msg = [message cStringUsingEncoding: kCFStringEncodingUTF8];
    logger::log(LogLevel::info, "%s", msg);
}

+ (void)verbose: (NSString*)message {
    const char* msg = [message cStringUsingEncoding: kCFStringEncodingUTF8];
    logger::log(LogLevel::verbose, "%s", msg);
}

+ (void)warning: (NSString*)message {
    const char* msg = [message cStringUsingEncoding: kCFStringEncodingUTF8];
    logger::log(LogLevel::warning, "%s", msg);
}

+ (void)error: (NSString*)message {
    const char* msg = [message cStringUsingEncoding: kCFStringEncodingUTF8];
    logger::log(LogLevel::error, "%s", msg);
}

@end
