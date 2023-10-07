
Run the test server thusly:

./gradlew  --no-daemon jettyRun

If you leave out the "--no-daemon" everything still works,
but you'll get a mess of error messages.

Same for running tests: 

./gradlew --no-daemon test

