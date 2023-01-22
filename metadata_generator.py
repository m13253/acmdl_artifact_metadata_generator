#!/usr/bin/env python3

import bs4
from bs4 import BeautifulSoup
import csv
import lxml  # noqa: F401, make sure BeautifulSoup can use lxml
import os
import re
from typing import List, Tuple, Set
import zipfile


# Change these configurations
PATH_ARTIFACTS_CSV = 'artifacts.csv'
PATH_ACMCMS_TOC_XML = 'acmcms-toc.xml'
PATH_OUTPUT = 'output'
CALLBACK_EMAIL = '****@*******.***'
PROCEEDING_NAME = 'PPoPP23'
PROCEEDING_PREFIX = 'ppopp23-p'
DATE_ISSUED = (2023, 1, 6)


def main() -> None:
    with open(PATH_ARTIFACTS_CSV, 'r', encoding='UTF-8-sig') as f:
        arti_csv = list(csv.DictReader(f))
    with open(PATH_ACMCMS_TOC_XML, 'rb') as f:
        toc_xml = BeautifulSoup(f, features='xml')
    try:
        os.mkdir(PATH_OUTPUT)
    except FileExistsError:
        pass

    while len(arti_csv) != 0 and all(i == '' for i in arti_csv[-1].values()):
        del arti_csv[-1]
    toc_papers = {
        paper.select_one(':scope > event_tracking_number').text.strip(): paper
        for paper in toc_xml.select('erights_record:scope > paper:has(> event_tracking_number)')
    }
    doi_regex = re.compile(r'https://doi\.org/(([.\d]+)/(zenodo\.[.\d]+))$')

    for row in arti_csv:
        tracking_number = row[f'{PROCEEDING_PREFIX}#'].strip()

        # Gather information from CSV
        csv_title = row['Title'].strip()
        avail_url = row['Available URL'].strip()
        badges = {value for column in ['Available', 'Functional', 'Reusable', 'Reproduced', 'Best'] for value in [row[column].strip()] if value != ''}

        # Gather information from XML
        toc_paper = toc_papers[f'{PROCEEDING_PREFIX}{tracking_number}']
        toc_title = toc_paper.select_one(':scope > paper_title').text.strip()
        if toc_title == csv_title:
            print(f'#{tracking_number}:\t{toc_title}')
        else:
            print(f'#{tracking_number} (XML):\t{toc_title}')
            print(f'#{tracking_number} (CSV):\t{csv_title}')

        if avail_url == 'Unavailable':
            print(f'(Info: Skipping #{tracking_number}.)')
            continue

        doi_match = doi_regex.match(avail_url)
        if doi_match is None:
            raise ValueError(f'{avail_url} is not a valid DOI URL')
        doi_full = doi_match.group(1)
        doi_prefix = doi_match.group(2)
        doi_suffix = doi_match.group(3)

        manifest_xml = create_manifest_xml(doi_prefix)
        zenodo_xml = create_zenodo_xml(toc_paper, doi_prefix, doi_full, badges)

        zip_path = os.path.join(PATH_OUTPUT, f'artifacts_{doi_suffix}_{DATE_ISSUED[0]:04}{DATE_ISSUED[1]:02}{DATE_ISSUED[2]:02}.zip')
        try:
            os.remove(zip_path)
        except FileNotFoundError:
            pass
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as f:
            zip_date = (DATE_ISSUED[0], DATE_ISSUED[1], DATE_ISSUED[2], 0, 0, 0)
            for path, data in [
                ('manifest.xml', manifest_xml),
                (f'{doi_suffix}/', None),
                (f'{doi_suffix}/meta/', None),
                (f'{doi_suffix}/meta/{doi_suffix}.xml', zenodo_xml),
            ]:
                zinfo = zipfile.ZipInfo(path, zip_date)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zinfo._compresslevel = 9
                zinfo.create_system = 3
                if data is None:
                    zinfo.external_attr = (0o40755 << 16) | 0x10
                    zinfo.CRC = 0
                    f.mkdir(zinfo, mode=0o755)
                else:
                    zinfo.external_attr = 0o644 << 16
                    f.writestr(zinfo, my_prettify(data))


def create_manifest_xml(doi_prefix: str) -> BeautifulSoup:
    doc = BeautifulSoup(features='xml')
    # /!DOCTYPE
    doc.append(bs4.Doctype('submission PUBLIC "-//Atypon//DTD Literatum Content Submission Manifest DTD v4.2 20140519//EN" "atypon/submissionmanifest.4.2.dtd"'))
    # /submission
    el_0 = append_tag(doc, doc, 'submission', attrs={'group-doi': f'{doi_prefix}/artifacts-group', 'submission-type': 'full'})
    # /submission/callback
    el_1 = append_tag(doc, el_0, 'callback')
    # /submission/callback/email
    append_tag(doc, el_1, 'email').append(CALLBACK_EMAIL)
    # /submission/processing-instructions
    el_1 = append_tag(doc, el_0, 'processing-instructions')
    # /submission/processing-instructions/make-live
    append_tag(doc, el_1, 'make-live', attrs={'on-condition': 'no-fatals'})
    return doc


def create_zenodo_xml(paper: bs4.Tag, doi_prefix: str, doi_full: str, badges: Set[str]) -> bs4.Tag:
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
    append_tag(doc, el_4, 'mods:identifier', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'type': 'doi'}).append(doi_full)
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo
    el_5 = append_tag(doc, el_4, 'mods:titleInfo', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'ID': 'title'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo/mods:title
    append_tag(doc, el_5, 'mods:title').append(paper.select_one(':scope > paper_title').text.strip())
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:titleInfo/mods:subTitle
    append_tag(doc, el_5, 'mods:subTitle')

    author_seqs: Set[int] = set()
    for author in paper.select(':scope > authors > author'):
        author_seq = int(author.select_one(':scope > sequence_no').text.strip())
        assert author_seq > 0
        assert author_seq not in author_seqs
        author_seqs.add(author_seq)
        prefix = author.select_one(':scope > prefix').text.strip()
        first_name = author.select_one(':scope > first_name').text.strip()
        middle_name = author.select_one(':scope > middle_name').text.strip()
        last_name = author.select_one(':scope > last_name').text.strip()
        suffix = author.select_one(':scope > suffix').text.strip()
        display_name = ' '.join(i for i in [prefix, first_name, middle_name, last_name, suffix] if i != '')
        email = author.select_one(':scope > email_address').text.strip()
        orcid = author.select_one(':scope > ORCID').text.strip()
        affiliation = author.select_one(':scope > affiliations > affiliation > institution').text.strip()

        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name
        el_5 = append_tag(doc, el_4, 'mods:name', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'ID': f'artseq-{author_seq - 1}'})
        # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:name/mods:namePart[@type='given']
        append_tag(doc, el_5, 'mods:namePart', attrs={'type': 'given'}).append(' '.join(i for i in [first_name, middle_name] if i != ''))
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

    for csv_id, xml_id, xml_desc in [
        ('#acm:artifacts-available', 'artifacts_available_v101', 'Artifacts Available'),
        ('#acm:artifacts-functional', 'artifacts_evaluated_functional_v101', 'Artifacts Evaluated — Functional'),
        ('#acm:artifacts-reusable', 'artifacts_evaluated_reusable_v101', 'Artifacts Evaluated — Reusable'),
        ('#acm:results-reproduced', 'results_reproduced_v101', 'Results Reproduced'),
    ]:
        if csv_id in badges:
            # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:subject[@ID='badges']/mods:topic
            append_tag(doc, el_5, 'mods:topic', attrs={'authority': xml_id}).append(xml_desc)

    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:relatedItem
    el_4.append(bs4.Comment(" FIXME: We don't know the DOI of the original article. "))
    # append_tag(doc, el_4, 'mods:relatedItem', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3', 'displayLabel': 'Related Article', 'xlink:href': '', 'ID': 'relatedDoi01'}).append('')
    el_4.append(bs4.Comment(f' <mods:relatedItem xmlns:mods="http://www.loc.gov/mods/v3" displayLabel="Related Article" xlink:href="{doi_prefix}/???" ID="relatedDoi01"></mods:relatedItem> '))
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension
    el_5 = append_tag(doc, el_4, 'mods:extension', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions
    el_6 = append_tag(doc, el_5, 'atpn:do-extensions', attrs={'xmlns:atpn': 'http://www.atypon.com/digital-objects', 'xsi:schemaLocation': 'http://www.atypon.com/digital-objects http://www.atypon.com/digital-objects/digital-objects.xsd'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:extension/atpn:do-extensions/atpn:description
    append_tag(doc, el_6, 'atpn:description').append(bs4.CData(f'<p>Artifact appendix item for {PROCEEDING_NAME}</p>'))
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
    append_tag(doc, el_6, 'atpn:baseDoi').append(f'{doi_prefix}/artifact-doe-class')
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:originInfo
    el_5 = append_tag(doc, el_4, 'mods:originInfo', attrs={'xmlns:mods': 'http://www.loc.gov/mods/v3'})
    # /mets/mets:dmdSec/mets:mdWrap/mets:xmlData/mods/mods:originInfo/mods:dateIssued
    append_tag(doc, el_5, 'mods:dateIssued', attrs={'encoding': 'iso8601'}).append(f'{DATE_ISSUED[0]}-{DATE_ISSUED[1]:02}-{DATE_ISSUED[2]:02}')
    # /mets/mets:structMap
    el_1 = append_tag(doc, el_0, 'mets:structMap', attrs={'xmlns:mets': 'http://www.loc.gov/METS/'})
    # /mets/mets:structMap/mets:div
    append_tag(doc, el_1, 'mets:div').append('')
    return doc


def append_tag(soup: BeautifulSoup, parent: bs4.Tag, *args, **kwargs) -> bs4.Tag:
    tag = soup.new_tag(*args, **kwargs)
    parent.append(tag)
    return tag


def my_prettify(xml: bs4.Tag) -> bytes:
    regex = re.compile(r'^( *)(<[^\n/][^\n]*)\n(?:\1  ([^\n<>]*)\n)?\1(</[^\n]*\n)', re.MULTILINE)
    return regex.sub(r'\1\2\3\4', xml.prettify(formatter=MyFormatter()) + '\n').encode('UTF-8')


class MyFormatter(bs4.formatter.XMLFormatter):
    def __init__(self, indent=2, *args, **kwargs) -> None:
        super().__init__(indent=indent, *args, **kwargs)

    def attributes(self, tag: bs4.Tag) -> List[Tuple[str, str]]:
        return [
            (k, (None if self.empty_attributes_are_booleans and v == '' else v))
            for k, v in list(tag.attrs.items())
        ]


if __name__ == '__main__':
    main()
