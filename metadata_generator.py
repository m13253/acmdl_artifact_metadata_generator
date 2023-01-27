#!/usr/bin/env python3

import bs4
from bs4 import BeautifulSoup
import csv
import html
import lxml  # noqa: F401, make sure BeautifulSoup can use lxml
import os
import re
from typing import Dict, List, Optional, Tuple, Set, TypeVar
import zipfile


# Change these configurations
PATH_ARTIFACTS_CSV = 'artifacts.csv'
PATH_ACMCMS_TOC_XML = 'acmcms-toc.xml'
PATH_OUTPUT = 'artifacts-metadata'
PROCEEDING_NAME = 'PPoPP23'
PROCEEDING_PREFIX = 'ppopp23-p'
CALLBACK_EMAIL = '****@*******.***'
DATE_ISSUED = (2023, 1, 6)


T = TypeVar('T')


def main() -> None:
    with open(PATH_ARTIFACTS_CSV, 'r', encoding='UTF-8-sig') as f:
        arti_csv = list(csv.DictReader(f))
    while len(arti_csv) != 0 and all(i == '' for i in arti_csv[-1].values()):
        del arti_csv[-1]  # Remove trailing empty lines
    with open(PATH_ACMCMS_TOC_XML, 'rb') as f:
        toc_xml = BeautifulSoup(f, features='xml')
    try:
        os.mkdir(PATH_OUTPUT)
    except FileExistsError:
        pass

    toc_papers = {
        unwrap(
            paper.select_one(':scope > event_tracking_number'),
            ValueError('Element /erights_record/paper/event_tracking_number is missing in XML')
        ).text.strip(): paper
        for paper in toc_xml.select('erights_record:scope > paper:has(> event_tracking_number)')
    }

    for arti_row in arti_csv:
        tracking_number = unwrap(
            arti_row.get(f'{PROCEEDING_PREFIX}#'),
            ValueError(f'Column {PROCEEDING_PREFIX}# is missing in CSV')
        ).strip()

        # Compare title between CSV and XML
        csv_title = unwrap(
            arti_row.get('Title'),
            ValueError("Column 'Title' is missing in CSV")
        ).strip()
        toc_paper = unwrap(
            toc_papers.get(f'{PROCEEDING_PREFIX}{tracking_number}'),
            ValueError(f'Tracking number #{tracking_number} is missing in XML'),
        )
        toc_title = unwrap(
            toc_paper.select_one(':scope > paper_title'),
            ValueError('Element /erights_record/paper/paper_title is missing in XML')
        ).text.strip()
        if toc_title == csv_title:
            print(f'#{tracking_number}:\t{toc_title}')
        else:
            print(f'#{tracking_number} (XML):\t{toc_title}')
            print(f'#{tracking_number} (CSV):\t{csv_title}')

        # Make sure the artifact URL is available
        arti_url = unwrap(
            arti_row.get('Available URL'),
            ValueError("Column 'Available URL' is missing in CSV")
        ).strip()
        if arti_url == 'Unavailable':
            print(f'(Info: Skipping #{tracking_number}.)')
            continue
        arti_doi = DOI(arti_url)

        # Make sure the paper DOI is a valid DOI
        doi = DOI(unwrap(
            arti_row.get('DOI'),
            ValueError("Column 'DOI' is missing in CSV")
        ).strip())

        manifest_xml = create_manifest_xml(arti_doi)
        zenodo_xml = create_zenodo_xml(toc_paper, arti_row)

        zip_path = os.path.join(PATH_OUTPUT, f'artifacts_{arti_doi.suffix}_{DATE_ISSUED[0]:04}{DATE_ISSUED[1]:02}{DATE_ISSUED[2]:02}.zip')
        try:
            os.remove(zip_path)
        except FileNotFoundError:
            pass
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as f:
            zip_date = (DATE_ISSUED[0], DATE_ISSUED[1], DATE_ISSUED[2], 0, 0, 0)
            for path, data in [
                ('manifest.xml', manifest_xml),
                (f'{arti_doi.suffix}/', None),
                (f'{arti_doi.suffix}/meta/', None),
                (f'{arti_doi.suffix}/meta/{arti_doi.suffix}.xml', zenodo_xml),
            ]:
                zinfo = zipfile.ZipInfo(path, zip_date)
                # For unknown reason, Python does not pass the global compression settings to each individual ZipInfo.
                # Using setattr to access private field is to bypass linter.
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                setattr(zinfo, '_compresslevel', 9)
                zinfo.create_system = 3  # POSIX
                if data is None:
                    # Again, for unknown reason, the POSIX mode is not passed in either.
                    zinfo.external_attr = (0o40755 << 16) | 0x10  # POSIX mode: drwxr-xr-x
                    zinfo.CRC = 0
                    f.mkdir(zinfo, mode=0o755)
                else:
                    zinfo.external_attr = 0o644 << 16  # POSIX mode: -rw-r--r--
                    f.writestr(zinfo, my_prettify(data))


def create_manifest_xml(arti_doi: 'DOI') -> BeautifulSoup:
    doc = BeautifulSoup(features='xml')
    # /!DOCTYPE
    doc.append(bs4.Doctype('submission PUBLIC "-//Atypon//DTD Literatum Content Submission Manifest DTD v4.2 20140519//EN" "atypon/submissionmanifest.4.2.dtd"'))
    # /submission
    el_0 = append_tag(doc, doc, 'submission', attrs={'group-doi': f'{arti_doi.prefix}/artifacts-group', 'submission-type': 'full'})
    # /submission/callback
    el_1 = append_tag(doc, el_0, 'callback')
    # /submission/callback/email
    append_tag(doc, el_1, 'email').append(CALLBACK_EMAIL)
    # /submission/processing-instructions
    el_1 = append_tag(doc, el_0, 'processing-instructions')
    # /submission/processing-instructions/make-live
    append_tag(doc, el_1, 'make-live', attrs={'on-condition': 'no-fatals'})
    return doc


def create_zenodo_xml(toc_paper: bs4.Tag, arti_row: Dict[str, str]) -> bs4.Tag:
    doc = BeautifulSoup(features='xml')
    # /mets
    el_0 = append_tag(doc, doc, 'mets', attrs={'xmlns': 'http://www.loc.gov/METS/', 'xmlns:xlink': 'http://www.w3.org/1999/xlink', 'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsi:schemaLocation': 'http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd', 'TYPE': 'artifact-doe'})
    # /mets/mets:dmdSec
    el_1 = append_tag(doc, el_0, 'mets:dmdSec', attrs={'xmlns:mets': 'http://www.loc.gov/METS/', 'ID': 'DMD'})
    # /mets/mets:dmdSec/mets:mdWrap
    el_2 = append_tag(doc, el_1, 'mets:mdWrap', attrs={'MDTYPE': 'MODS'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData
    el_3 = append_tag(doc, el_2, 'mets:xmlData')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods
    el_4 = append_tag(doc, el_3, 'mods', attrs={'xmlns': 'http://www.loc.gov/mods/v3', 'xsi:schemaLocation': 'http://www.loc.gov/mods/v3 http://www.loc.gov/standards/mods/v3/mods.xsd'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:identifier
    arti_doi = DOI(unwrap(
        arti_row.get('Available URL'),
        ValueError("Column 'Available URL' is missing in CSV")
    ).strip())
    append_tag(doc, el_4, 'mods:identifier', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'type': 'doi'}).append(arti_doi.full)
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo
    el_5 = append_tag(doc, el_4, 'mods:titleInfo', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'ID': 'title'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo/mods:title
    append_tag(doc, el_5, 'mods:title').append(unwrap(
        toc_paper.select_one(':scope > paper_title'),
        ValueError('Element /erights_record/paper/paper_title is missing in XML')
    ).text.strip())
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo/mods:subTitle
    append_tag(doc, el_5, 'mods:subTitle')

    author_seqs: Set[int] = set()
    for author in toc_paper.select(':scope > authors > author'):
        author_seq = int(unwrap(
            author.select_one(':scope > sequence_no'),
            ValueError('Element /erights_record/paper/authors/author/sequence_no is missing in XML')
        ).text.strip())
        assert author_seq > 0
        assert author_seq not in author_seqs
        author_seqs.add(author_seq)
        prefix = unwrap(
            author.select_one(':scope > prefix'),
            ValueError('Element /erights_record/paper/authors/author/prefix is missing in XML')
        ).text.strip()
        first_name = unwrap(
            author.select_one(':scope > first_name'),
            ValueError('Element /erights_record/paper/authors/author/first_name is missing in XML')
        ).text.strip()
        middle_name = unwrap(
            author.select_one(':scope > middle_name'),
            ValueError('Element /erights_record/paper/authors/author/middle_name is missing in XML')
        ).text.strip()
        last_name = unwrap(
            author.select_one(':scope > last_name'),
            ValueError('Element /erights_record/paper/authors/author/last_name is missing in XML')
        ).text.strip()
        suffix = unwrap(
            author.select_one(':scope > suffix'),
            ValueError('Element /erights_record/paper/authors/author/suffix is missing in XML')
        ).text.strip()
        display_name = ' '.join(i for i in [prefix, first_name, middle_name, last_name, suffix] if i != '')
        email = unwrap(
            author.select_one(':scope > email_address'),
            ValueError('Element /erights_record/paper/authors/author/email_address is missing in XML')
        ).text.strip()
        orcid = unwrap(
            author.select_one(':scope > ORCID'),
            ValueError('Element /erights_record/paper/authors/author/ORCID is missing in XML')
        ).text.strip()
        affiliation = unwrap(
            # Note: This only finds the first affiliation
            author.select_one(':scope > affiliations > affiliation > institution'),
            ValueError('Element /erights_record/paper/authors/author/affiliations/affiliation/institution is missing in XML')
        ).text.strip()

        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name
        el_5 = append_tag(doc, el_4, 'mods:name', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'ID': f'artseq-{author_seq - 1}'})
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:namePart[@type='given']
        append_tag(doc, el_5, 'mods:namePart', attrs={'type': 'given'}).append(
            # I see some submissions join their first names and middle names together
            ' '.join(i for i in [first_name, middle_name] if i != '')
        )
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:namePart[@type='family']
        append_tag(doc, el_5, 'mods:namePart', attrs={'type': 'family'}).append(last_name)
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:namePart[@type='termsOfAddress']
        append_tag(doc, el_5, 'mods:namePart', attrs={'type': 'termsOfAddress'}).append('')
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:displayForm
        append_tag(doc, el_5, 'mods:displayForm').append(display_name)
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:nameIdentifier
        append_tag(doc, el_5, 'mods:nameIdentifier', attrs={'type': 'ORCID'}).append(orcid)
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:role
        el_6 = append_tag(doc, el_5, 'mods:role')
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:role/mods:roleTerm
        append_tag(doc, el_6, 'mods:roleTerm').append('Contributor')
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:nameIdentifier
        append_tag(doc, el_5, 'mods:nameIdentifier', attrs={'type': 'email'}).append(email)
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:affiliation
        append_tag(doc, el_5, 'mods:affiliation').append(affiliation)

    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:subject[@ID='type']
    el_5 = append_tag(doc, el_4, 'mods:subject', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'authority': 'artifact_type', 'ID': 'type'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:subject[@ID='type']/mods:topic
    append_tag(doc, el_5, 'mods:topic', attrs={'authority': 'artfc-software'}).append('software')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:subject[@ID='badges']
    el_5 = append_tag(doc, el_4, 'mods:subject', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'authority': 'reproducibility-types', 'ID': 'badges'})

    badges = {
        value
        for column in ['Available', 'Functional', 'Reusable', 'Replicated', 'Reproduced', 'Best']
        for value in [unwrap(
            arti_row.get(column),
            ValueError(f'Column {column!r} is missing in CSV')
        ).strip()]
        if value != ''
    }
    for csv_id, xml_id, xml_desc in [
        ('#acm:artifacts-available', 'artifacts_available_v101', 'Artifacts Available'),
        ('#acm:artifacts-functional', 'artifacts_evaluated_functional_v101', 'Artifacts Evaluated — Functional'),
        ('#acm:artifacts-reusable', 'artifacts_evaluated_reusable_v101', 'Artifacts Evaluated — Reusable'),
        ('#acm:results-replicated', 'results_replicated_v101', 'Results Replicated'),
        ('#acm:results-reproduced', 'results_reproduced_v101', 'Results Reproduced'),
    ]:
        if csv_id in badges:
            # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:subject[@ID='badges']/mods:topic
            append_tag(doc, el_5, 'mods:topic', attrs={'authority': xml_id}).append(xml_desc)

    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:relatedItem
    doi = DOI(unwrap(
        arti_row.get('DOI'),
        ValueError("Column 'DOI' is missing in CSV")
    ).strip())
    append_tag(doc, el_4, 'mods:relatedItem', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'displayLabel': 'Related Article', 'xlink:href': doi.full, 'ID': 'relatedDoi01'}).append('')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension
    el_5 = append_tag(doc, el_4, 'mods:extension', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions
    el_6 = append_tag(doc, el_5, 'atpn:do-extensions', attrs={'xmlns:atpn': 'http://www.atypon.com/digital-objects', 'xsi:schemaLocation': 'http://www.atypon.com/digital-objects http://www.atypon.com/digital-objects/digital-objects.xsd'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:description
    append_tag(doc, el_6, 'atpn:description').append(bs4.CData(f'<p>Artifact appendix item for {html.escape(PROCEEDING_NAME)}</p>'))
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:copyright
    append_tag(doc, el_6, 'atpn:copyright').append('Author(s)')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:version
    append_tag(doc, el_6, 'atpn:version').append('1.0')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:softwareDependencies
    append_tag(doc, el_6, 'atpn:softwareDependencies')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:hardwareDependencies
    append_tag(doc, el_6, 'atpn:hardwareDependencies')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:installation
    append_tag(doc, el_6, 'atpn:installation')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:otherInstructions
    append_tag(doc, el_6, 'atpn:otherInstructions')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:eiInstallation
    append_tag(doc, el_6, 'atpn:eiInstallation')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:eiParameterization
    append_tag(doc, el_6, 'atpn:eiParameterization')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:eiEvaluation
    append_tag(doc, el_6, 'atpn:eiEvaluation')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:eiWorkflow
    append_tag(doc, el_6, 'atpn:eiWorkflow')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:eiOtherInstructions
    append_tag(doc, el_6, 'atpn:eiOtherInstructions')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:dataDocumentation
    append_tag(doc, el_6, 'atpn:dataDocumentation')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:provenance
    append_tag(doc, el_6, 'atpn:provenance').append('')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:accessCondition
    append_tag(doc, el_6, 'atpn:accessCondition').append('free')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:licenseUrl
    append_tag(doc, el_6, 'atpn:licenseUrl')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:keywords
    append_tag(doc, el_6, 'atpn:keywords', attrs={'nested-label': 'NONE'}).append('')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:baseDoi
    append_tag(doc, el_6, 'atpn:baseDoi').append(f'{arti_doi.prefix}/artifact-doe-class')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:originInfo
    el_5 = append_tag(doc, el_4, 'mods:originInfo', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:originInfo/mods:dateIssued
    append_tag(doc, el_5, 'mods:dateIssued', attrs={'encoding': 'iso8601'}).append(f'{DATE_ISSUED[0]}-{DATE_ISSUED[1]:02}-{DATE_ISSUED[2]:02}')
    # /mets/mets:structMap
    el_1 = append_tag(doc, el_0, 'mets:structMap', attrs={'xmlns:mets': 'http://www.loc.gov/METS/'})
    # /mets/mets:structMap/mets:div
    append_tag(doc, el_1, 'mets:div').append('')
    return doc


def unwrap(value: Optional[T], msg: BaseException) -> T:
    if value is None:
        raise msg
    return value


def append_tag(soup: BeautifulSoup, parent: bs4.Tag, *args, **kwargs) -> bs4.Tag:
    tag = soup.new_tag(*args, **kwargs)
    parent.append(tag)
    return tag


def my_prettify(xml: bs4.Tag) -> bytes:
    # Joins leaf nodes into a single line
    return re.sub(
        r'^( *)(<[^\n/].*)\n(?:\1  ([^\n<>]*)\n)?\1(</.*\n)',
        r'\1\2\3\4',
        xml.prettify(formatter=MyFormatter()) + '\n',
        flags=re.MULTILINE
    ).encode('UTF-8')


class DOI:
    def __init__(self, doi: str) -> None:
        self.url = doi

    @property
    def full(self) -> str:
        return f'{self.prefix}/{self.suffix}'

    @full.setter
    def full(self, doi: str) -> None:
        self.url = doi

    @property
    def url(self) -> str:
        return f'https://doi.org/{self.prefix}/{self.suffix}'

    @url.setter
    def url(self, doi: str) -> None:
        doi_match = unwrap(
            re.match(r'(?:doi:|https?://(?:dx\.)?doi\.org/)?(10.[.\d]+)/([^/]+)$', doi),
            ValueError(f'{doi!r} is not a valid DOI URL')
        )
        prefix, suffix = doi_match.group(1), doi_match.group(2)
        assert prefix is not None
        assert suffix is not None
        self.prefix, self.suffix = prefix, suffix


class MyFormatter(bs4.formatter.XMLFormatter):
    def __init__(self, *args, **kwargs) -> None:
        kwargs['indent'] = kwargs.get('indent', 2)
        super().__init__(*args, **kwargs)

    def attributes(self, tag: bs4.Tag) -> List[Tuple[str, Optional[str]]]:
        return [
            (k, (None if self.empty_attributes_are_booleans and v == '' else v))
            for k, v in list(tag.attrs.items())
        ]


if __name__ == '__main__':
    main()
