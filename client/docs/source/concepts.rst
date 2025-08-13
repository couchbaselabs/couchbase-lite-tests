Concepts
========

Test Development Kit (TDK)
--------------------------

The deliverable of this project is called the Test Development Kit, or TDK for short.  It is like an SDK, and you can use it in the same way.  The only difference is that it is meant to be consumed by the testing library pytest, rather than a python program written by someone.  At the highest level it is divided into two phases:  *orchestration* and *execution*.  

Orchestration
-------------

This is the phase in which resources are assembled according to what is needed in the execution phase.  Currently in the TDK there are two ways to do this, but the method of doing this is not restrained in any way.  The only requirement is that the orchestration phase output a compatible config.json file for the execution phase to use.

The first method (deprecated) is via docker.  The docker compose file in the environment folder will create a single Sync Gateway and Couchbase Server instance for use as your backend.  

The second method is via AWS.  The environment/aws folder contains many details about this but you can spin up as many Couchbase Server, Sync Gateway, and load balancer instances as you need.  This is the recommended way to perform orchestration.

Execution
---------

This is the phase in which tests are executed using pytest.  The only input requirement is a config.json file which described where all of the relevant resources are located.  You can see an `example <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/tests/dev_e2e/config.example.json>`_ of this in the repo.  Passing this config file via ``--config`` to pytest will allow all of the tests to have direct access to any resources listed inside.