#include "FileDownloader.h"

#import <Foundation/Foundation.h>
#import <Foundation/NSURLSession.h>
#import <stdexcept>
#import <string>

namespace ts::support {
    void FileDownloader::download(const std::string &url, const std::string &destinationPath) {
        @autoreleasepool {
            NSURL* nsUrl = [NSURL URLWithString: [NSString stringWithUTF8String: url.c_str()]];
            if (!nsUrl) {
                throw std::invalid_argument("Invalid URL: " + url);
            }

            NSURL* destUrl = [NSURL fileURLWithPath: [NSString stringWithUTF8String: destinationPath.c_str()]];
            if (!destUrl) {
                throw std::invalid_argument("Invalid destination path: " + destinationPath);
            }

            dispatch_semaphore_t sema = dispatch_semaphore_create(0);

            __block NSError* error = nil;
            NSURLSessionConfiguration* config = [NSURLSessionConfiguration ephemeralSessionConfiguration];
            NSURLSession* session = [NSURLSession sessionWithConfiguration: config];
            NSURLSessionDownloadTask* task = [session downloadTaskWithURL: nsUrl completionHandler:
                                              ^(NSURL *location, NSURLResponse* response, NSError* err) {
                if (err) {
                    error = err;
                } else {
                    NSFileManager* fileManager = [NSFileManager defaultManager];
                    [fileManager moveItemAtURL: location toURL: destUrl error: &error];
                }
                dispatch_semaphore_signal(sema);
            }];
            [task resume];
            dispatch_semaphore_wait(sema, DISPATCH_TIME_FOREVER);

            [session finishTasksAndInvalidate];

            if (error) {
                throw std::runtime_error([error.localizedDescription UTF8String]);
            }
        }
    }
}