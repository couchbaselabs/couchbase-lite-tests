#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface TSTestServer : NSObject

+ (instancetype) shared;

- (instancetype)init NS_UNAVAILABLE;

- (void)start;

- (void)stop;

@end

NS_ASSUME_NONNULL_END
