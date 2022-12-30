"""Shared constants."""

# Wiktionary dump URL
# {0}: current locale
# {1}: dump date
BASE_URL = "https://dumps.wikimedia.org/{0}wiktionary"
DUMP_URL = f"{BASE_URL}/{{1}}/{{0}}wiktionary-{{1}}-pages-meta-current.xml.bz2"

# Wikimedia REST API
WIKIMEDIA_HEADERS = {"User-Agent": "https://github.com/BoboTiG/ebook-reader-dict"}
WIKIMEDIA_URL_BASE = "https://en.wikipedia.org/api/rest_v1"
WIKIMEDIA_URL_MATH_CHECK = f"{WIKIMEDIA_URL_BASE}/media/math/check/{{type}}"
WIKIMEDIA_URL_MATH_RENDER = (
    f"{WIKIMEDIA_URL_BASE}/media/math/render/{{format}}/{{hash}}"
)

# GitHub stuff
# {0}: current locale
REPOS = "BoboTiG/ebook-reader-dict"
GH_REPOS = f"https://github.com/{REPOS}"
DOWNLOAD_URL_DICTFILE = f"{GH_REPOS}/releases/download/{{0}}/dict-{{0}}-{{0}}.df.bz2"
DOWNLOAD_URL_KOBO = f"{GH_REPOS}/releases/download/{{0}}/dicthtml-{{0}}-{{0}}.zip"
DOWNLOAD_URL_STARDICT = f"{GH_REPOS}/releases/download/{{0}}/dict-{{0}}-{{0}}.zip"
