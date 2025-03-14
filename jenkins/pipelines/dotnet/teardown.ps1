Import-Module $PSScriptRoot/prepare_env.psm1 -Force

$env:PYTHONPATH = "$PSScriptRoot\..\..\..\"
Push-Location $PSScriptRoot\..\..\..\environment\aws
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python .\stop_backend.py --topology topology.json
Pop-Location