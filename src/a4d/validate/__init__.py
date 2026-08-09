"""Post-pipeline validation that compares cleaned output against raw source.

Used by ``scripts/validate_source_vs_output.py``. The validator does not import
or modify either golden cleaning module (clean/patient.py, clean/product.py);
it replicates only the small slices of logic it needs.
"""
