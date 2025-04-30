$env:PYTHONPATH = "$PSScriptRoot\..\..\..\"
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Global
Push-Location $AWS_ENVIRONMENT_DIR
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python .\stop_backend.py --topology topology_setup\topology.json
Pop-Location