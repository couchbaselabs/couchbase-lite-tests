#import "TSLogger.h"
#include "Log.h"

using namespace ts::log;

@implementation TSLogger

+ (void)info:(NSString *)message {
    const char *msg = [message cStringUsingEncoding:kCFStringEncodingUTF8];
    Log::log(LogLevel::info, "%s", msg);
}

+ (void)verbose:(NSString *)message {
    const char *msg = [message cStringUsingEncoding:kCFStringEncodingUTF8];
    Log::log(LogLevel::verbose, "%s", msg);
}

+ (void)warning:(NSString *)message {
    const char *msg = [message cStringUsingEncoding:kCFStringEncodingUTF8];
    Log::log(LogLevel::warning, "%s", msg);
}

+ (void)error:(NSString *)message {
    const char *msg = [message cStringUsingEncoding:kCFStringEncodingUTF8];
    Log::log(LogLevel::error, "%s", msg);
}

@end
