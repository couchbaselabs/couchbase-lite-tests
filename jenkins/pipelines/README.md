## Jenkins Pipelines

The jenkins pipelines are running end-to-end-tests consisting of the main pipeline for triggering the platform test jobs and the platform test pipelines.

### Main Pipeline

The main pipeline, defined in `main/Jenkinsfile`, is responsible for triggering platform test jobs for a given CBL version and build and triggered daily.

When the pipeline is executed, the pipeline will trigger the test job for all platforms including Android, java, c, net, and iOS to run the end-to-end tests. The pipeline will automatically detect the latest successful build of the specified version of CBL. The pipeline will record the CBL version and build number and will trigger the test job for the same CBL version and build number only once.

### Platform Test Pipelines

The platform test pipelines are defined in `<platform-name>/Jenkinsfile`. Each platform test pipeline may run end-to-end tests on multiple sub-platforms that are supported. 

To run the tests, the pipeline performs the following steps. Firstly, the pipeline builds the Test Server application using the specified CBL version and build number. Next, the environment is started by running CBS/SG in the docker container. Once the environment is up and running, the Test Server application is started. When both environment and Test Server are up and ready, the pipeline will run the pytest tests. When the tests are done, the pipeline will shutdown the envinronment and the Test Server application.
