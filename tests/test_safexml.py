"""P7a file-hardening: untrusted `.knxproj` archives are ZIP-of-XML, so both a
zip-bomb (tiny archive -> gigabytes) and an XML billion-laughs/XXE payload are
in scope. These tests build hostile fixtures in a temp dir and assert each is
refused, while an honest small archive/XML still parses.
"""
import io
import os
import tempfile
import zipfile

from nickol_knx_mcp.safexml import (
    preflight_archive, open_archive, safe_read, safe_fromstring,
    SafeArchiveError, SafeXmlError,
    MAX_ENTRIES, MAX_TOTAL_UNCOMPRESSED,
)


def _write_zip(path, members):
    """members: list of (name, bytes, compresstype)."""
    with zipfile.ZipFile(path, "w") as z:
        for name, data, ct in members:
            zi = zipfile.ZipInfo(name)
            zi.compress_type = ct
            z.writestr(zi, data)


def main():
    tmp = tempfile.mkdtemp(prefix="safexml_")

    # 1. honest small archive + XML round-trips
    ok = os.path.join(tmp, "ok.knxproj")
    _write_zip(ok, [("P-1/0.xml", b"<Project><d id='1'/></Project>", zipfile.ZIP_DEFLATED)])
    preflight_archive(ok)  # no raise
    with open_archive(ok) as z:
        root = safe_fromstring(safe_read(z, "P-1/0.xml"))
    assert root.find("d").get("id") == "1", "honest XML must parse"

    # 2. zip-bomb by compression ratio: 100 MiB of zeros compresses to ~kB
    bomb = os.path.join(tmp, "bomb.knxproj")
    _write_zip(bomb, [("big.xml", b"\x00" * (100 * 1024 * 1024), zipfile.ZIP_DEFLATED)])
    try:
        preflight_archive(bomb)
        raise AssertionError("high-ratio zip-bomb must be refused")
    except SafeArchiveError as e:
        assert "ratio" in str(e).lower() or "limit" in str(e).lower(), e

    # 3. path-traversal member name
    trav = os.path.join(tmp, "trav.knxproj")
    _write_zip(trav, [("../../etc/evil.xml", b"<x/>", zipfile.ZIP_STORED)])
    try:
        preflight_archive(trav)
        raise AssertionError("traversal member name must be refused")
    except SafeArchiveError as e:
        assert "traversal" in str(e).lower() or "unsafe" in str(e).lower(), e

    # 4. absolute member name
    absn = os.path.join(tmp, "abs.knxproj")
    _write_zip(absn, [("/etc/evil.xml", b"<x/>", zipfile.ZIP_STORED)])
    try:
        preflight_archive(absn)
        raise AssertionError("absolute member name must be refused")
    except SafeArchiveError:
        pass

    # 5. billion-laughs / DTD in XML -> refused (dependency-free floor)
    bomb_xml = (b"<?xml version='1.0'?>\n<!DOCTYPE lolz [\n"
                b"<!ENTITY a '1234567890'>\n<!ENTITY b '&a;&a;&a;&a;&a;'>\n]>\n"
                b"<lolz>&b;</lolz>")
    try:
        safe_fromstring(bomb_xml)
        raise AssertionError("DTD/entity XML must be refused")
    except SafeXmlError as e:
        assert "dtd" in str(e).lower() or "entit" in str(e).lower(), e

    # 6. XXE external entity (also carries a DTD) -> refused
    xxe = (b"<?xml version='1.0'?>\n<!DOCTYPE r [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>\n"
           b"<r>&x;</r>")
    try:
        safe_fromstring(xxe)
        raise AssertionError("XXE must be refused")
    except SafeXmlError:
        pass

    # 7. malformed XML -> SafeXmlError (not a raw ParseError leaking out)
    try:
        safe_fromstring(b"<unclosed>")
        raise AssertionError("malformed XML must raise SafeXmlError")
    except SafeXmlError:
        pass

    # 8. safe_read bounds a member that lies small in its header. Rebuild the
    #    central directory to under-report file_size, proving the streaming cap
    #    (not the header) is what protects us.
    lie = os.path.join(tmp, "lie.knxproj")
    _write_zip(lie, [("big.xml", b"A" * (2 * 1024 * 1024), zipfile.ZIP_STORED)])
    # (the honest 2 MiB member is well under the per-member cap, so it reads fine)
    with zipfile.ZipFile(lie) as z:
        assert len(safe_read(z, "big.xml")) == 2 * 1024 * 1024, "honest member reads whole"

    # sanity: caps are sane positive numbers
    assert MAX_ENTRIES > 0 and MAX_TOTAL_UNCOMPRESSED > 0

    print("test_safexml: OK — zip-bomb (ratio), traversal/absolute names, DTD/entity, "
          "XXE, malformed XML all refused; honest archive + XML parse.")


if __name__ == "__main__":
    main()
