# Executed environment

The project reuses the user's already installed IIC-OSIC-TOOLS container. Docker, the image and PDK were not reinstalled. The executable project directory is `/foss/designs/thermobridge`, on the Ubuntu Linux filesystem. Work and netlist outputs are writable as UID/GID 1000:1000.

The exact observations are in [environment.json](../reports/environment.json). The image is `hpretl/iic-osic-tools:2026.10`, native AMD64 digest `sha256:9201d2ebe74a406cf6af850ca2c646ac0462f3b2cea94cd98cb6580d8ceef800`. Windows host RAM is 16 GB. The WSL VM reports about 7.6 GiB RAM, the tool container has a 6 GiB limit, and physical flows use two workers. The Linux virtual disk's advertised free capacity is not host capacity: approximately 9 GB remained on Windows C: at the initial inspection. Large intermediates stay outside Git.

Primary process: SKY130A, `sky130_fd_sc_hd`, nominal core voltage 1.8 V. Installed open_pdks revision: `1689ac3f2dc763876eaf967227c7dfe831b031ae`. All primary digital Liberty/LEF/GDS and verification files come from this installed process. The external microhotplate is an assumed physical model, not a SKY130 MEMS device.

Observed tools: LibreLane 3.1.0.dev3, Yosys 0.70 (`28ba3cb92`), OpenROAD `26Q4-407-geb14e40b7`, KLayout 0.30.12, ngspice 47, Python 3.12.3, NumPy 2.5.4, SciPy 1.18.1, Matplotlib 3.11.2, pytest 9.1.1 and cocotb 2.1.0. See the JSON for paths and executable probe results.

## First physical smoke gate

The installed upstream 32-bit counter example was copied under `build/smoke` with its original authorship header intact. It is an environment test, not a research result. LibreLane's complete classic flow produced final DEF/GDS/LEF/netlists/SDC/SPEF and completed Magic DRC, KLayout DRC and Netgen LVS. The original example used a 20 ns clock. Its final metrics are archived separately from controller results in `reports/smoke/metrics.json`.

## Reproduction from Windows

The authoritative Git checkout is on Windows. `scripts/container.py sync` copies scoped source files into the existing writable container project directory. It does not pull an image or change other designs. Use `python scripts/container.py run ...` to execute commands and `fetch` for selected outputs. Inside the container or a Linux checkout, use the documented Make targets directly.

GitHub API routing initially timed out. A process-local alternate GitHub API address, with normal HTTPS hostname/certificate verification, succeeded. The collaborator audit contains the authenticated login and invitation status, not credentials. No machine-wide DNS settings were changed.
