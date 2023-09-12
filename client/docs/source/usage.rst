Usage
=====

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

- *event_loop* : Likely not used directly by the tests, but overrides the default event loop present in pytest sessions to a long lasting one that allows the reuse of a single Couchbase Server connection
- *cblpytest* : Probably the most important fixture of them all.  This contains a preconfigured top level object which is a factory for all other classes that the test will use (see the above Getting Started section)
- *dataset_path* : The path on disk to the data files that the TDK will make use of (such as sync gateway configuration files, etc)

The above are all defined in a file called ``conftest.py`` at the root of a directory containing tests