Running Smoke Tests
===================

You can write a config file by copying config_in.json to config.json and adding in a "test-servers" array entry yourself, or alternatively if you want to streamline multiple devices for some reason you can copy topology.example.json to topology.json, edit the various fields and add more entries as you please and then run the following:

`python ../../environment/aws/start_backend.py --topology ./topology.json --tdk-config-out ./config.json --tdk-config-in ./config_in.json`

This will read from config_in.json, build and run the services defined in topology.json and write the resulting config to config.json.

After that it's just standard pytest stuff (e.g. `pytest -v --no-header --config config.json`)