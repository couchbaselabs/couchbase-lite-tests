# Minification rules for the Android test server.
#
# Enable R8 minification for the jak Android test server so that 
# the build exercises the consumer ProGuard rules bundled in the 
# Couchbase Lite AAR the same way a customer app does.

# Keep readable stack traces in test reports.
-keepattributes SourceFile,LineNumberTable
