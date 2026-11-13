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

            // Copied out of the handler: its autoreleased objects are freed before the wait returns.
            __block std::string errorMessage;
            NSURLSessionConfiguration* config = [NSURLSessionConfiguration ephemeralSessionConfiguration];
            NSURLSession* session = [NSURLSession sessionWithConfiguration: config];
            NSURLSessionDownloadTask* task = [session downloadTaskWithURL: nsUrl completionHandler:
                                              ^(NSURL *location, NSURLResponse* response, NSError* err) {
                NSInteger status = [response isKindOfClass: [NSHTTPURLResponse class]] ? ((NSHTTPURLResponse*)response).statusCode : 0;
                NSError* moveError = nil;
                if (err) {
                    errorMessage = err.localizedDescription.UTF8String;
                } else if (status != 200) {
                    errorMessage = "Failed to download file from URL '" + url + "' : " + std::to_string(status);
                } else if (![[NSFileManager defaultManager] moveItemAtURL: location toURL: destUrl error: &moveError]) {
                    errorMessage = moveError.localizedDescription.UTF8String;
                }
                dispatch_semaphore_signal(sema);
            }];
            [task resume];
            dispatch_semaphore_wait(sema, DISPATCH_TIME_FOREVER);

            [session finishTasksAndInvalidate];

            if (!errorMessage.empty()) {
                throw std::runtime_error(errorMessage);
            }
        }
    }
}