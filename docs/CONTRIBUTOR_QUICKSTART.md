# ThermoBridge contributor quick start

ThermoBridge uses a host Git checkout together with an existing IIC-OSIC-TOOLS Docker container.

## Host setup

```bash
mkdir -p ~/Dev/Projects
cd ~/Dev/Projects
git clone https://github.com/aminemons/project.git project
cd project

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install reportlab PyMuPDF



