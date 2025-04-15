$env:PYTHONPATH = "$PSScriptRoot\..\..\..\"
Push-Location $PSScriptRoot\..\..\..\..\environment\aws
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python .\stop_backend.py --topology topology_setup\topology.json
Pop-Location