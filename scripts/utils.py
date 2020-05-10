"""Utilities."""
import re
from typing import List
from warnings import warn

from .lang import (
    templates_italic,
    templates_ignored,
    templates_multi,
    templates_other,
    template_warning_skip,
)
from . import constants as C


def capitalize(text: str) -> str:
    """Capitalize the first letter only.

        >>> capitalize("alice")
        'Alice'
        >>> capitalize("BOB")
        'BOB'
        >>> capitalize("alice and bob")
        'Alice and bob'
    """
    return f"{text[0].capitalize()}{text[1:]}"


def format_chimy(composition: List[str]) -> str:
    """Format chimy notations.

        >>> format_chimy(["H", "2", "O"])
        'H<sub>2</sub>O'
        >>> format_chimy(["FeCO", "3", ""])
        'FeCO<sub>3</sub>'
    """
    return "".join(f"<sub>{c}</sub>" if c.isdigit() else c for c in composition)


def handle_name(word: str, parts: List[str]) -> str:
    """Handle the 'name' template to display writers/authors or any full name person.

        >>> handle_name("foo", ["nom w pc", "Aldous", "Huxley"])
        "Aldous <span style='font-variant:small-caps'>Huxley</span>"
        >>> handle_name("foo", ["nom w pc", "L. L. Zamenhof"])
        'L. L. Zamenhof'
    """
    res = parts[1]
    if len(parts) > 2:
        res += f" <span style='font-variant:small-caps'>{parts[2]}</span>"
    else:
        warn(f"Malformed template in the Wikicode of {word!r} (parts={parts})")
    return res


def handle_sport(tpl: str, parts: List[str]) -> str:
    """Handle the 'sport' template.

        >>> handle_sport("sport", [""])
        '<i>(Sport)</i>'
        >>> handle_sport("sport", ["sport", "fr", "collectif"])
        '<i>(Sport collectif)</i>'
    """
    res = f"<i>({capitalize(tpl)}"
    if len(parts) >= 3:
        # {{sport|fr|collectif}}
        res += f" {parts[2]}"
    res += ")</i>"
    return res


def handle_term(text: str) -> str:
    """Format a term.

        >>> handle_term("")
        ''
        >>> handle_term("foo")
        '<i>(Foo)</i>'
        >>> handle_term("Foo")
        '<i>(Foo)</i>'
        >>> handle_term("<i>(Foo)</i>")
        '<i>(Foo)</i>'
    """
    if text.startswith("<i>("):
        return text
    elif not text:
        return ""
    return f"<i>({capitalize(text)})</i>"


def handle_unit(parts: List[str]) -> str:
    """Pretty format a 'unit'.

        >>> handle_unit(["92", "%"])
        '92%'
    """
    return "".join(parts)


def int_to_roman(number: int) -> str:
    """
    Convert an integer to a Roman numeral.
    Source: https://www.oreilly.com/library/view/python-cookbook/0596001673/ch03s24.html

        >>> int_to_roman(12)
        'XII'
        >>> int_to_roman(19)
        'XIX'
        >>> int_to_roman(2020)
        'MMXX'
    """

    # if not 0 < number < 4000:
    #     raise ValueError("Argument must be between 1 and 3999")
    ints = (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1)
    nums = ("M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I")
    result = []
    for i in range(len(ints)):
        count = int(number / ints[i])
        result.append(nums[i] * count)
        number -= ints[i] * count
    return "".join(result)


#
# Internal use only!
#


def is_ignored(word: str) -> bool:
    """Helper to filter out words from the final dictionary.

        >>> is_ignored("accueil")
        False
        >>> is_ignored("2")
        True
        >>> is_ignored("22")
        True
        >>> is_ignored("222")
        True
        >>> is_ignored("222" * 12)
        True
        >>> is_ignored("")
        True
        >>> is_ignored(" ")
        True
    """

    # Filter out "small" words and numbers
    return len(word) < 3 or word.isnumeric()


def clean(word: str, text: str) -> str:
    """Cleans up the provided Wikicode.
    Removes templates, tables, parser hooks, magic words, HTML tags and file embeds.
    Keeps links.
    Source: https://github.com/macbre/mediawiki-dump/blob/3f1553a/mediawiki_dump/tokenizer.py#L8

        >>> clean("foo", "{{unknown}}")
        '<i>(Unknown)</i>'
        >>> clean("foo", "<span style='color:black'>[[♣]]</span>")
        "<span style='color:black'>♣</span>"
        >>> clean("foo", "{{foo|{{bar}}|123}}")
        ''
    """

    # Speed-up lookup
    sub = re.sub

    # Basic formatting
    text = sub(r"'''?([^']+)'''?", "\\1", text)

    # Parser hooks
    text = sub(r"<ref[^>]+>[^<]+</ref[^>]+>", "", text)  # <ref>foo</ref> -> ''

    # HTML
    text = sub(r"<br[^>]+/?>", "", text)  # <br> / <br />
    text = text.replace("&nbsp;", " ")

    # Files
    # [[File:picture.svg|vignette|120px|'''Base''' d’or ''(sens héraldique)'']] -> ''
    text = sub(r"\[\[.+:[^|\]]+(?:\|[^\]]+){2,}\]\]", "", text)

    # Local links
    text = sub(r"\[\[([^|\]]+)\]\]", "\\1", text)  # [[a]] -> a
    text = sub(r"\[\[[^|]+\|([^\]]+)\]\]", "\\1", text)  # [[a|b]] -> b

    text = text.replace("[[", "").replace("]]", "")

    # Tables
    text = sub(r"{\|[^}]+\|}", "", text)  # {|foo..|}

    # Headings
    text = sub(
        r"^=+\s?([^=]+)\s?=+",
        lambda matches: matches.group(1).strip(),
        text,
        flags=re.MULTILINE,
    )  # == a == -> a

    # Files and other links with namespaces
    text = sub(r"\[\[[^:\]]+:[^\]]+\]\]", "", text)  # [[foo:b]] -> ''

    # External links
    text = sub(
        r"\[http[^\s]+ ([^\]]+)\]", "\\1", text
    )  # [[http://example.com foo]] -> foo
    text = sub(r"https?://[^\s]+", "", text)  # remove http://example.com

    # Lists
    text = sub(r"^\*+\s?", "", text, flags=re.MULTILINE)

    # Magic words
    text = sub(r"__\w+__", "", text)  # __TOC__

    # Remove extra quotes left
    text = text.replace("''", "")

    # Templates
    # {{foo}}
    # {{foo|bar}}
    # {{foo|{{bar}}|123}}
    # {{foo|{{bar|baz}}|123}}

    # Simplify the parsing logic: this line will return a list of nested templates.
    for tpl in set(re.findall(r"({{[^{}]*}})", text)):
        # Transform the nested template.
        # This will remove any nested templates from the original text.
        text = text.replace(tpl, transform(word, tpl[2:-2]))

    # Now that all nested templates are done, we can process top-level ones
    while "{{" in text:
        start = text.find("{{")
        pos = start + 2
        subtext = ""

        while pos < len(text):
            if text[pos : pos + 2] == "}}":
                # We hit the end of the template
                pos += 1
                break

            # Save the template contents
            subtext += text[pos]
            pos += 1

        # The template is now completed
        transformed = transform(word, subtext)
        text = f"{text[:start]}{transformed}{text[pos + 1 :]}"

    # Remove extra spaces
    text = sub(r"\s{2,}", " ", text)
    text = sub(r"\s{1,}\.", ".", text)

    return text.strip()


def transform(word: str, template: str) -> str:
    """Handle the data inside the *text* template.

        >>> transform("foo", "w|ISO 639-3")
        'ISO 639-3'
        >>> transform("test", "w|Gesse aphaca|Lathyrus aphaca")
        'Lathyrus aphaca'
        >>> transform("foo", "grammaire|fr")
        '<i>(Grammaire)</i>'
        >>> transform("foo", "conj|grp=1|fr")
        ''
        >>> transform("test", "w | ISO 639-3")
        'ISO 639-3'
    """

    parts_raw = template.split("|")
    parts = [p.strip() for p in parts_raw]
    tpl = parts[0]

    # Help fixing formatting on Wiktionary (some templates are more complex and cannot be fixed)
    if parts != parts_raw and tpl not in template_warning_skip[C.LOCALE]:
        warn(f"Extra spaces found in the Wikicode of {word!r} (parts={parts_raw})")

    if tpl in templates_ignored[C.LOCALE]:
        return ""

    # {{w|ISO 639-3}} -> ISO 639-3
    # {{w|Gesse aphaca|Lathyrus aphaca}} -> Lathyrus aphaca
    if tpl == "w":
        return parts[-1]

    if tpl in templates_multi[C.LOCALE]:
        res: str = eval(templates_multi[C.LOCALE][tpl])
        return res

    if tpl in templates_italic[C.LOCALE]:
        return f"<i>({templates_italic[C.LOCALE][tpl]})</i>"

    if tpl in templates_other[C.LOCALE]:
        return templates_other[C.LOCALE][tpl]

    # {{grammaire|fr}} -> (Grammaire)
    if len(parts) == 2:
        return f"<i>({capitalize(tpl)})</i>"

    # {{conj|grp=1|fr}} -> ''
    if len(parts) > 2:
        return ""

    # May need custom handling in lang/$LOCALE.py
    return f"<i>({capitalize(tpl)})</i>" if tpl else ""
