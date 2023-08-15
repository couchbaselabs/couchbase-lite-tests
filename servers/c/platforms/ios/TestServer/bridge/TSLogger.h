//
//  Log.h
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 8/14/23.
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface TSLogger : NSObject

+ (void)info: (NSString*)message;
+ (void)verbose: (NSString*)message;
+ (void)warning: (NSString*)message;
+ (void)error: (NSString*)message;

@end

NS_ASSUME_NONNULL_END
