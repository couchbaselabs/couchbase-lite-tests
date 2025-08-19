TDK Usage
=========

Getting started
---------------

You might be wondering how to get started with the TDK.  Unfortunately that is not a simple answer, and depends on a lot on the semantics of the test that you are writing.  However, for the vast majority of the time you will likely be using the contents of the :func:`cbltest.api <cbltest.api>` namespace.  

The best way to learn is to look at the existing tests, but some common classes you will probably be using in every test are some of the following:

- :func:`cblpytest <cbltest.CBLPyTest>`: The top level class that is passed into each test function
- :func:`syncgateway <cbltest.api.syncgateway>`: A class for interacting with the REST API of Sync Gateway
- :func:`couchbaseserver <cbltest.api.couchbaseserver>`: A class for interacting with Couchbase Server (via the python SDK)
- :func:`cloud <cbltest.api.cloud>`: A class for performing actions that involve multiple coordinated steps between the above
- :func:`testserver <cbltest.api.testserver>`: A class for interacting with the test servers built from this repo

Test Parameters
---------------

These are not defined by the TDK, but rather the test writer (with possible help from TDK devs).  The parameters make use of the concept of `pytest fixtures <https://docs.pytest.org/en/stable/explanation/fixtures.html>`_ and so the tests can use as many or as few as they prefer.  Currently, the tests in the TDK repo define several fixtures as follows:

- *dataset_path* : The path on disk to the data files that the TDK will make use of (such as sync gateway configuration files, etc)

The above is defined in a file called ``conftest.py`` at the root of a directory containing tests

Orchestrator Usage
------------------

See the `following README <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/environment/aws/README.md>`_ for more information about orchestration but the basic idea for those looking to make use of the AWS orchestrator is to create a topology file, and then pass it to a function called ``start_backend`` along with some other information.  You can see an example of this in the `.NET Test Setup Script <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/jenkins/pipelines/dotnet/setup_test.py>`_.  