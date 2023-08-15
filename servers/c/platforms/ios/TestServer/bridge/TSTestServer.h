#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface TSTestServer : NSObject

+ (void)initialize;

- (instancetype)init;

- (void)start;

- (void)stop;

@end

NS_ASSUME_NONNULL_END
