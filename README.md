# acmdl_artifact_metadata_generator

Small program to generate XML metadata for ACMDL artifacts.

ACMDL uses a very complicated XML format for metadata. This program may help you generate them.

## Third-party dependencies

Please use `pip` to install the following dependencies:
* [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)
* [lxml](https://pypi.org/project/lxml/)

## Usage

To use this program, you need to modify the configuration options in `metadata_generator.py`, and also provide `artifacts.csv` and `acmcms-toc.xml`. This repository includes two sample files for your reference.

If the available URL of any artifact entry is `Unavailable` (spelled exactly), that entry will be skipped.

Then, run `python metadata_generator.py` to generate the metadata.

The output files will be located in `artifacts-metadata` folder. Each submission will generate a ZIP file, each containing two XML files.

## Compatibility

This program is written in Python 3.11. It may or may not work with earlier versions of Python 3, but I have not tested it.

Compatibility patches are welcome.

## Acknowledgements

Thanks [Anjo Vahldiek-Oberwagner](https://github.com/vahldiek/acmdl_artifact_metadata) for his program as my reference.

However, this program is a complete rewrite and does not use his code.
