New-Item -ItemType Directory -Force -Path "data\raw"
New-Item -ItemType Directory -Force -Path "data\supporting"
New-Item -ItemType Directory -Force -Path "db"
New-Item -ItemType Directory -Force -Path "output"
New-Item -ItemType Directory -Force -Path "reports\tearsheets"
New-Item -ItemType Directory -Force -Path "reports\sector"
New-Item -ItemType Directory -Force -Path "reports\portfolio"
New-Item -ItemType Directory -Force -Path "tests\etl"
New-Item -ItemType Directory -Force -Path "tests\kpi"
New-Item -ItemType Directory -Force -Path "tests\api"
New-Item -ItemType Directory -Force -Path "tests\dq"
New-Item -ItemType Directory -Force -Path "notebooks"

Copy-Item -Path "c:\Users\amit0\OneDrive\Desktop\nifty100_datasets\n100\*.xlsx" -Destination "data\raw\" -Force
Copy-Item -Path "c:\Users\amit0\OneDrive\Desktop\nifty100_datasets\n100\supporting datasets\*.xlsx" -Destination "data\supporting\" -Force

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pre-commit.exe install
