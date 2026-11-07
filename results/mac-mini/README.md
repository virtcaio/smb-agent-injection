# Offline detector runs on a second machine

These two runs of `scripts/detector_offline.py` were made on 6 November 2026 on a Mac mini (Apple silicon) by the working session that prepared prompt-armor 0.9.4, not by the study's own pipeline:

- `detector-offline-0.9.3`: prompt-armor 0.9.3, with the L2 and L3 model files copied from a repository checkout instead of downloaded on first use.
- `detector-offline-0.9.4-dev`: an editable install of the 0.9.4 branch before the release.

The study's numbers use the runs in `results/detector-offline-<version>/`, made on the MacBook with the PyPI releases, the same machine as the in-agent runs. These are kept as a cross-machine check: against the MacBook run of 0.9.3, 116 of the 3,100 decisions differ (3.7%). That fits the 0.9.3 L3 computing in INT8, which rounds differently per CPU, but the model files were also obtained differently, so the two causes are not separated here.
