"""Hardened parsing of untrusted ``.knxproj`` / ``.knxprod`` archives.

A ``.knxproj`` is a ZIP of XML that a user hands us from elsewhere — so it is
untrusted input. Two classic attack classes apply and both are cheap to defuse:

* **XML** — billion-laughs entity expansion and XXE external-entity fetches.
  Legitimate KNX project XML never carries a ``<!DOCTYPE``/``<!ENTITY``, so we
  reject any document that does (a dependency-free floor), and additionally use
  ``defusedxml`` when installed (robust parser-level blocking).
* **ZIP** — zip-bombs (a tiny archive that decompresses to gigabytes) and
  path-traversal member names. We pre-flight the archive against absolute
  size/entry caps and read each member through a bounded reader, so a member
  whose header lies about its size still can't exhaust memory.

Everything here is read-only and report-friendly: on a violation we raise
``SafeArchiveError``/``SafeXmlError`` with a plain message the callers turn into
a normal ``{"error": ...}`` result rather than a traceback.
"""
from __future__ import annotations

import os
import zipfile
from typing import Optional

# Absolute caps. Real projects sit far below these; they exist to bound the
# damage a hostile archive can do, not to constrain honest ones.
MAX_ARCHIVE_BYTES = 1 * 1024 * 1024 * 1024        # 1 GiB on-disk .knxproj
MAX_ENTRIES = 200_000                              # members in the archive
MAX_MEMBER_UNCOMPRESSED = 512 * 1024 * 1024        # 512 MiB per decompressed member
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024    # 2 GiB decompressed total
MAX_RATIO = 1000                                   # per-member compression ratio


class SafeArchiveError(Exception):
    """A ZIP archive failed a safety pre-flight (size, entries, ratio, name)."""


class SafeXmlError(Exception):
    """An XML document was rejected as unsafe (DTD/entity present) or malformed."""


def _is_unsafe_name(name: str) -> bool:
    """Absolute paths, drive letters, or ``..`` traversal in a member name.

    We only ever ``read()`` members in-memory, never extract to disk, so this is
    defense-in-depth — but a traversal name is a reliable hostile-archive signal.
    """
    if not name or name.startswith(("/", "\\")):
        return True
    if len(name) >= 2 and name[1] == ":":  # windows drive, e.g. C:
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def preflight_archive(path: str) -> None:
    """Validate a ``.knxproj``/``.knxprod`` before any member is read.

    Raises ``SafeArchiveError`` on: missing file, oversize archive, bad ZIP,
    too many members, a traversal member name, or declared sizes that exceed the
    per-member / total / ratio caps (a zip-bomb declares its own blow-up).
    """
    if not os.path.isfile(path):
        raise SafeArchiveError(f"file not found: {path}")
    size = os.path.getsize(path)
    if size > MAX_ARCHIVE_BYTES:
        raise SafeArchiveError(
            f"archive is {size} bytes, over the {MAX_ARCHIVE_BYTES}-byte limit")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise SafeArchiveError(f"not a valid ZIP/.knxproj: {e}") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise SafeArchiveError(
                f"{len(infos)} entries, over the {MAX_ENTRIES} limit")
        total = 0
        for info in infos:
            if _is_unsafe_name(info.filename):
                raise SafeArchiveError(
                    f"unsafe member name (traversal/absolute): {info.filename!r}")
            usize = info.file_size
            if usize > MAX_MEMBER_UNCOMPRESSED:
                raise SafeArchiveError(
                    f"member {info.filename!r} declares {usize} bytes, over the "
                    f"{MAX_MEMBER_UNCOMPRESSED}-byte per-member limit")
            if info.compress_size > 0 and usize / info.compress_size > MAX_RATIO:
                raise SafeArchiveError(
                    f"member {info.filename!r} compression ratio "
                    f"{usize // max(info.compress_size, 1)}:1 exceeds {MAX_RATIO}:1 "
                    "(possible zip-bomb)")
            total += usize
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise SafeArchiveError(
                    f"decompressed total exceeds the {MAX_TOTAL_UNCOMPRESSED}-byte limit")


def open_archive(path: str) -> zipfile.ZipFile:
    """Pre-flight ``path`` then return an open ``ZipFile``.

    Callers should read members via :func:`safe_read` so a member whose header
    under-declares its true size is still bounded. Raises ``SafeArchiveError``.
    """
    preflight_archive(path)
    return zipfile.ZipFile(path)


def safe_read(zf: zipfile.ZipFile, name: str, pwd: Optional[bytes] = None) -> bytes:
    """Read one member, hard-capped at ``MAX_MEMBER_UNCOMPRESSED`` bytes.

    Uses a streaming reader and stops one byte past the cap, so a member that
    lies about its size in the central directory still cannot exhaust memory.
    """
    with zf.open(name, pwd=pwd) as fh:
        data = fh.read(MAX_MEMBER_UNCOMPRESSED + 1)
    if len(data) > MAX_MEMBER_UNCOMPRESSED:
        raise SafeArchiveError(
            f"member {name!r} decompressed past the {MAX_MEMBER_UNCOMPRESSED}-byte "
            "limit (possible zip-bomb)")
    return data


def _has_dtd(data: bytes) -> bool:
    """True if the XML prolog declares a DTD or entities.

    Scans a bounded head of the document (declarations must precede the root
    element). Legitimate ETS project XML never carries these; their presence is
    the vector for billion-laughs and XXE, so we treat it as hostile.
    """
    head = data[:65536].lstrip()
    lowered = head.lower()
    return b"<!doctype" in lowered or b"<!entity" in lowered


def safe_fromstring(data: bytes):
    """Parse XML bytes into an Element, rejecting DTD/entity/external attacks.

    Applies a dependency-free DTD/entity reject first (a floor that holds even
    without ``defusedxml``), then parses with ``defusedxml`` when available and
    falls back to the stdlib parser otherwise. Raises ``SafeXmlError`` on an
    unsafe or malformed document.
    """
    if _has_dtd(data):
        raise SafeXmlError(
            "XML declares a DTD/entities — refused (billion-laughs/XXE vector; "
            "legitimate .knxproj XML never contains one)")
    try:
        try:
            from defusedxml.ElementTree import fromstring as _defused
            return _defused(data, forbid_dtd=True, forbid_entities=True,
                            forbid_external=True)
        except ImportError:
            import xml.etree.ElementTree as ET
            return ET.fromstring(data)
    except SafeXmlError:
        raise
    except Exception as e:  # noqa: BLE001  (ParseError and defusedxml's *Forbidden)
        raise SafeXmlError(f"unsafe or malformed XML: {e}") from e
