# Sources and application context

Checked 27 October 2026. Recheck any application or tool details before acting on them.

## EPFL E3

- [Application](https://eee.epfl.ch/apply/): summer 2027 closes **1 November 2026, 23:55 Swiss time**. On that date Switzerland and Algeria both use UTC+1, so the deadline is also 23:55 Algiers time. Application changes are unavailable after submission. Prepare a CV, complete transcripts, motivation letter and ID. The application page explicitly permits English or French transcripts.
- [Eligibility and selection](https://eee.epfl.ch/selection-criteria/): enrolled Bachelor/Master students throughout the internship; at least the second Bachelor year completed at application. Selection criteria include top-10% standing, a high GPA, research motivation and plans for doctoral study. An integrated engineering programme should be described accurately with official enrollment evidence; do not invent an intermediate Bachelor or unearned equivalence.
- [Research domains](https://eee.epfl.ch/labs/): **VLSI design**, **Nanoelectronics**, **Multiphysics simulations** are all listed. Choose these exact labels for the user's stated interests.
- [FAQ](https://eee.epfl.ch/faq/): no required English certificate; enter GPA on the school's original scale. Projects are discussed with recruiting laboratories rather than selected from a predefined project list. A motivation letter of at most about two pages is recommended. Recommendation letters may be uploaded as additional attachments and are not mandatory.
- [Hosting database](https://eee.epfl.ch/e3-host-labs/): its table did not expose lab entries in the text retrieval used for this brief. The shortlist below is based on verified research fit, **not confirmed 2027 hosting availability**. Check the live database/application selector before choosing laboratories.

## Research-fit shortlist

| Laboratory | Verified direction | Fit to this project | Limit |
|---|---|---|---|
| [ESL — Embedded Systems Laboratory](https://www.epfl.ch/labs/esl/research/), David Atienza | Hardware/software co-design, energy-efficient architectures, open-source SoCs, thermal modelling | Strongest overall connection: compact thermal models, efficient fixed-point hardware and measured implementation trade-offs | Microheater physics is an application of related methods, not a claim that ESL currently advertises this exact internship |
| [NanoLab — Nanoelectronic Devices Laboratory](https://www.epfl.ch/labs/nanolab/), Adrian Ionescu | Technology, design and modelling of nanoscale devices; energy-efficient edge systems and sensing | Sensor-interface robustness, device variability/noise and physics-to-circuit reasoning | A mature-node controller and synthetic sensor model alone do not demonstrate novel nanodevice fabrication |
| [LSI — Integrated Systems Laboratory](https://www.epfl.ch/labs/lsi/), Giovanni De Micheli | Design automation, logic synthesis, circuit/system optimization | Bit-width and arithmetic architecture exploration with verified area/timing trade-offs | Thermal application alone is weaker evidence of synthesis-method research; emphasize the actual hardware experiment |

These are candidates to verify, not a promise of lab places. EPFL selects applicants individually; a two-person project does not imply paired admission.

## Toolchain and existing public work

- [IIC-OSIC-TOOLS](https://github.com/iic-jku/iic-osic-tools): upstream README lists sky130A, gf180mcuD and IHP PDKs; tools include Xschem, ngspice, Yosys, OpenROAD, LibreLane, Magic, Netgen, KLayout and Gmsh. Upstream currently describes LibreLane as the successor of OpenLane(2). The installed image may differ: record its actual digest and versions.
- [SKY130 PDK documentation](https://skywater-pdk.readthedocs.io/): authoritative device, model and process documentation. Verify device voltage/temperature limits and the exact installed libraries.
- [LibreLane](https://github.com/librelane/librelane): inspect the installed version's help and supported example before authoring flow configuration.
- [Ishaq's profile](https://github.com/Ishaq-ML/Ishaq-ML): identifies Micro-Nanoelectronics studies, ML, FPGA, signal processing and optimization interests.
- [Ishaq's ECG/FPGA project](https://github.com/Ishaq-ML/ecg-cnn-fpga-deployment): public README describes a multi-objective CNN search, quantization and FPGA-oriented pipeline. These are repository claims, not independently reproduced results. Some implementation sections credit another named contributor; do not transfer their contributions or hardware claims to this project.
- [GitHub collaborator API](https://docs.github.com/en/rest/collaborators/collaborators): invitation requires adequate repository-administration permission. `permission=push` is ordinary write access; invitation is not acceptance.

## How to describe the work in an application

State only the last verified release: problem, model assumptions, experiment, numerical result with uncertainty, implemented hardware, and remaining limitation. Cite the repository plus a frozen commit/release. Describe the current work as an independent extension of interests/experience in electrothermal sensing; claim a connection to earlier CDTA work only to the extent Amine can substantiate it. Do not publish confidential internship data.

Report academic standing exactly as documented by the home institution; do not rescale grades, invent a rank or claim a numerical acceptance probability. Prior experience and project evidence demonstrate research fit but do not remove EPFL's academic-selection criteria.
