# acmdl_artifact_metadata_generator

Small program to generate XML metadata for ACMDL artifacts.

ACMDL uses a very complicated XML format for metadata. This program may help you generate them.

## Usage

To use this program, you need to modify the configuration options in `metadata_generator.py`, and also provide `artifacts.csv` and `acmcms-toc.xml`.

The output files will be located in `output` folder. Each submission will generate a ZIP file, each containing two XML files.

## Acknowledgements

Thanks [Anjo Vahldiek-Oberwagner](https://github.com/vahldiek/acmdl_artifact_metadata) for his reference program. However, this program is a complete rewrite.
