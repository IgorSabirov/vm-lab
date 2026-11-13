# X26 v0.3 physical run

Authoritative scope: RUN_CONTRACT.md + PHYSICAL_MANIFEST.json + x26r040/physical.py.
Inherited v0.1/v0.2 README/templates/CHECKS are historical, not this run's readiness receipt.
The old full manifest is deliberately rejected. Use:

    python -m unittest discover -s tests -v
    python -m x26r040.physical_cli --manifest PHYSICAL_MANIFEST.json --outdir NEW_DIR --mode preflight

Main requires the pinned bundle, a target-VM calibration, and its matching runtime gate.
The conditional model and the run are authorized by the user's 9 November instruction.
No ADD derivation, spontaneous symmetry breaking, autonomous resource reproduction,
or correspondence to the authors' exact named-graph model is asserted.
