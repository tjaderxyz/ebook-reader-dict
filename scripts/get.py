"""Retrieve and purge Wiktionary data."""
import bz2
import json
import os
import re
import sys
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Generator, List, Optional, Pattern, Tuple, TYPE_CHECKING

import requests
from requests.exceptions import HTTPError
import wikitextparser as wtp
import wikitextparser._spans

from .lang import patterns
from .utils import clean
from . import annotations as T
from . import constants as C

if TYPE_CHECKING:  # pragma: nocover
    from xml.etree.ElementTree import Element  # noqa


# As stated in wikitextparser._spans.parse_pm_pf_tl():
#   If the byte_array passed to parse_to_spans contains n WikiLinks, then
#   this function will be called n + 1 times. One time for the whole byte_array
#   and n times for each of the n WikiLinks.
#
# We do not care about links, let's speed-up the all process by skipping the n times call.
# Doing that is a ~30% optimization.
wikitextparser._spans.WIKILINK_FINDITER = lambda *_: ()


def decompress(file: Path) -> Path:
    """Decompress a BZ2 file."""
    output = file.with_suffix(file.suffix.replace(".bz2", ""))
    if output.is_file():
        return output

    msg = f">>> Uncompressing into {output.name}:"
    print(msg, end="", flush=True)

    comp = bz2.BZ2Decompressor()
    with file.open("rb") as fi, output.open(mode="wb") as fo:
        total = 0
        for data in iter(partial(fi.read, 1024 * 1024), b""):
            uncompressed = comp.decompress(data)
            fo.write(uncompressed)
            total += len(uncompressed)
            print(f"\r{msg} {total:,} bytes", end="", flush=True)
    print(f"\r{msg} OK [{output.stat().st_size:,} bytes]", flush=True)

    return output


def fetch_snapshots() -> List[str]:
    """Fetch available snapshots.
    Return a list of sorted dates.
    """
    with requests.get(C.BASE_URL) as req:
        req.raise_for_status()
        return sorted(re.findall(r'href="(\d+)/"', req.text))


def fetch_pages(date: str) -> Path:
    """Download all pages, current versions only.
    Return the path of the XML file BZ2 compressed.
    """
    output_xml = C.SNAPSHOT / f"pages-{date}.xml"
    output = C.SNAPSHOT / f"pages-{date}.xml.bz2"
    if output.is_file() or output_xml.is_file():
        return output

    msg = f">>> Fetching {C.WIKI}-{date}-pages-meta-current.xml.bz2:"
    print(msg, end="", flush=True)

    url = f"{C.BASE_URL}/{date}/{C.WIKI}-{date}-pages-meta-current.xml.bz2"
    with output.open(mode="wb") as fh, requests.get(url, stream=True) as req:
        req.raise_for_status()
        total = 0
        for chunk in req.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)
                total += len(chunk)
                print(f"\r{msg} {total:,} bytes", end="", flush=True)
    print(f"\r{msg} OK [{output.stat().st_size:,} bytes]", flush=True)

    return output


def find_definitions(word: str, sections: T.Sections) -> List[str]:
    """Find all definitions, without eventual subtext."""
    definitions = list(
        chain.from_iterable(
            find_section_definitions(word, section) for section in sections
        )
    )
    if not definitions:
        return []

    # Remove duplicates
    seen = set()
    return [d for d in definitions if not (d in seen or seen.add(d))]  # type: ignore


def find_section_definitions(
    word: str,
    section: wtp.Section,
    pattern: Pattern[str] = re.compile(r"^((?:<i>)?\([\w ]+\)(?:</i>)?\.? ?\??…?)*$"),
) -> Generator[str, None, None]:
    """Find definitions from the given *section*, without eventual subtext.

    The *pattern* will be used to filter out:
        - empty definitions like "(Maçonnerie) (Reliquat)"
        - almost-empty definitions, like "(Poésie) …"
        (or definitions using a sublist, it is not yet handled)
    """
    lists = section.get_lists()
    if lists:
        definitions = (clean(word, d.strip()) for d in lists[0].items)
        yield from (d for d in definitions if not pattern.match(d))


def find_genre(code: str, pattern: Pattern[str] = C.GENRE) -> str:
    """Find the genre."""
    match = pattern.search(code)
    return match.group(1) if match else ""


def find_pronunciation(code: str, pattern: Pattern[str] = C.PRONUNCIATION) -> str:
    """Find the pronunciation."""
    match = pattern.search(code)
    return match.group(1) if match else ""


def find_sections(code: str) -> Generator[str, None, None]:
    """Find the correct section(s) holding the current locale definition(s)."""
    sections = wtp.parse(code).get_sections(include_subsections=False)
    yield from (
        section
        for section in sections
        if section.title and section.title.lstrip().startswith(patterns[C.LOCALE])
    )


def get_and_parse_word(word: str, raw: bool = False) -> None:
    """Get a *word* wikicode and parse it."""
    with requests.get(C.WORD_URL.format(word)) as req:
        code = req.text

    pronunciation, genre, defs = parse_word(word, code, force=True)

    print(word, f"\\{pronunciation}\\", f"({genre}.)", "\n")
    for i, definition in enumerate(defs, start=1):
        if not raw:
            # Strip HTML tags
            definition = re.sub(r"<[^>]+/?>", "", definition)
        print(f"{i}.".rjust(4), definition)


def guess_snapshots() -> List[str]:
    """Retrieve available snapshots."""
    # Check if we want to force the use of a specific snapshot
    from_env = os.getenv("WIKI_DUMP", "")
    if from_env:  # pragma: nocover
        print(
            f">>> WIKI_DUMP is set to {from_env}, regenerating dictionaries ...",
            flush=True,
        )
        return [from_env]

    # Get all available snapshots
    return fetch_snapshots()


def parse_word(word: str, code: str, force: bool = False) -> Tuple[str, str, List[str]]:
    """Parse *code* Wikicode to find word details.
    *force* can be set to True to force the pronunciation and genre guessing.
    It is disabled by default t spee-up the overall process, but enabled when
    called from get_and_parse_word().
    """
    sections = find_sections(code)
    pronunciation = ""
    genre = ""
    definitions = find_definitions(word, sections)

    if definitions or force:
        pronunciation = find_pronunciation(code)
        genre = find_genre(code)

    return pronunciation, genre, definitions


def process(file: Path) -> T.Words:
    """Process the big XML file and retain only information we are interested in."""

    words: T.Words = {}

    print(f">>> Processing {file} ...", flush=True)

    for element in xml_iter_parse(str(file)):
        word, code = xml_parse_element(element)
        if len(word) < 2 or ":" in word:
            continue

        try:
            pronunciation, genre, definitions = parse_word(word, code)
        except Exception:  # pragma: nocover
            print(f"ERROR with {word!r}")
        else:
            if definitions:
                words[word] = pronunciation, genre, definitions

    return words


def save(snapshot: str, words: T.Words) -> None:
    """Persist data."""
    # This file is needed by convert.py
    with C.SNAPSHOT_DATA.open(mode="w", encoding="utf-8") as fh:
        json.dump(words, fh, sort_keys=True)

    C.SNAPSHOT_COUNT.write_text(str(len(words)))
    C.SNAPSHOT_FILE.write_text(snapshot)

    print(f">>> Saved {len(words):,} words into {C.SNAPSHOT_DATA}", flush=True)


def xml_iter_parse(file: str) -> Generator["Element", None, None]:
    """Efficient XML parsing for big files.
    Elements are yielded when they meet the "page" tag.
    """
    import xml.etree.ElementTree as etree

    doc = etree.iterparse(file, events=("start", "end"))
    _, root = next(doc)

    start_tag = None

    for event, element in doc:
        if (
            start_tag is None
            and event == "start"
            and element.tag == "{http://www.mediawiki.org/xml/export-0.10/}page"
        ):
            start_tag = element.tag
        elif start_tag is not None and event == "end" and element.tag == start_tag:
            yield element
            start_tag = None

            # Keep memory low
            root.clear()


def xml_parse_element(element: "Element") -> Tuple[str, str]:
    """Parse the *element* to retrieve the word and its definitions."""
    revision = element[3]
    if revision.tag == "{http://www.mediawiki.org/xml/export-0.10/}restrictions":
        # When a word is "restricted", then the revision comes just after
        revision = element[4]
    elif not revision:
        # This is a "redirect" page, not interesting.
        return "", ""

    # The Wikicode can be at different indexes, but not ones lower than 5
    for info in revision[5:]:
        if info.tag == "{http://www.mediawiki.org/xml/export-0.10/}text":
            code = info.text or ""
            break
    else:
        # No Wikicode, maybe an unfinished page.
        return "", ""

    word = element[0].text or ""  # title
    return word, code


def main(word: Optional[str] = "", raw: bool = False) -> int:
    """Extry point."""

    # Fetch one word and parse it, used for testing mainly
    if word:
        get_and_parse_word(word, raw=raw)
        return 0

    # Ensure the folder exists
    C.SNAPSHOT.mkdir(exist_ok=True, parents=True)

    # Get the snapshot to handle
    snapshots = guess_snapshots()
    snapshot = snapshots[-1]

    # Fetch and uncompress the snapshot file
    try:
        file = fetch_pages(snapshot)
    except HTTPError:
        print(" FAIL", flush=True)
        print(">>> Wiktionary dump is ongoing ... ", flush=True)
        print(">>> Will use the previous one.", flush=True)
        snapshot = snapshots[-2]
        file = fetch_pages(snapshot)

    file = decompress(file)

    # Process the XML to retain only primary information
    words = process(file)
    if not words:  # pragma: nocover
        raise ValueError("Empty dictionary?!")

    # Save data for next runs
    save(snapshot, words)

    print(">>> Retrieval done!", flush=True)
    return 0


if __name__ == "__main__":  # pragma: nocover
    sys.exit(main())
