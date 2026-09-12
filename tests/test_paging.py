"""Stable ordering and cursor paging for the two tools whose natural result is large
(`list_group_addresses`, `get_devices`).

Why this exists: the old implementation returned a bare list truncated at `limit`, in
whatever order the parser happened to produce, with no signal that anything was cut. A
retry could therefore return a different page, and a caller could not tell a complete
answer from a truncated one (raised in r/mcp, 2026-09-12).
"""
import random

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp import server as srv


def _ga(addr, name, dm=1, ds=1):
    return {"name": name, "identifier": f"G{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dm, "sub": ds}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _project(shuffled: bool) -> dict:
    addrs = [f"{m}/{mid}/{sub}" for m in (1, 2, 10) for mid in (0, 3) for sub in (1, 2, 12)]
    if shuffled:
        random.Random(7).shuffle(addrs)          # parser order is not address order
    gas = {a: _ga(a, f"GA {a}") for a in addrs}   # bare 1.001, no domain word -> category unknown
    devs = {ia: {"individual_address": ia, "name": f"dev {ia}", "order_number": "X",
                 "manufacturer_name": "M", "communication_object_ids": [], "channels": {}}
            for ia in (["1.1.10", "1.1.2", "1.2.1", "10.1.1", "1.1.1"] if shuffled
                       else ["1.1.1", "1.1.2", "1.1.10", "1.2.1", "10.1.1"])}
    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": devs,
           "functions": {}, "topology": {}, "group_ranges": {}}
    return raw


def _all_pages(fn, key, page_size):
    out, cursor, guard = [], None, 0
    while True:
        res = fn(limit=page_size, cursor=cursor)
        out.extend(res[key])
        cursor = res["next_cursor"]
        guard += 1
        assert guard < 50, "cursor never terminated"
        if cursor is None:
            return out, res["total_matched"]


def main():
    # the same project, once in address order and once shuffled by the "parser"
    for shuffled in (False, True):
        srv._STATE["project"] = build_loaded_from_raw(_project(shuffled), "paging.knxproj")

        res = srv.list_group_addresses(limit=5)
        addrs = [g["address"] for g in res["group_addresses"]]
        # 1. numeric, not lexical: 1/0/2 before 1/0/12, and main 2 before main 10
        assert addrs == ["1/0/1", "1/0/2", "1/0/12", "1/3/1", "1/3/2"], addrs
        # 2. truncation is never silent
        assert res["total_matched"] == 18 and res["returned"] == 5, res
        assert res["next_cursor"] == "1/3/2", res["next_cursor"]

        # 3. paging covers everything exactly once, in order, whatever the page size
        for size in (1, 5, 7, 18, 100):
            got, total = _all_pages(lambda **kw: srv.list_group_addresses(**kw),
                                    "group_addresses", size)
            seen = [g["address"] for g in got]
            assert total == 18 and len(seen) == 18 and len(set(seen)) == 18, (size, len(seen))
            assert seen == sorted(seen, key=srv._ga_sort_key), size

        # 4. devices: individual addresses sort numerically, same contract
        d = srv.get_devices(limit=3)
        assert [x["individual_address"] for x in d["devices"]] == ["1.1.1", "1.1.2", "1.1.10"], d
        assert d["total_matched"] == 5 and d["next_cursor"] == "1.1.10"
        devs, total = _all_pages(lambda **kw: srv.get_devices(**kw), "devices", 2)
        assert total == 5 and [x["individual_address"] for x in devs] == \
            ["1.1.1", "1.1.2", "1.1.10", "1.2.1", "10.1.1"], devs

        # 5. filters still work and are reflected in total_matched
        f = srv.list_group_addresses(kind="command", limit=100)
        assert f["total_matched"] == f["returned"] == 18 and f["next_cursor"] is None, f

    # 6. the last page of one run equals the last page of a re-parsed, reshuffled project
    srv._STATE["project"] = build_loaded_from_raw(_project(False), "paging.knxproj")
    a = srv.list_group_addresses(limit=4, cursor="1/3/2")
    srv._STATE["project"] = build_loaded_from_raw(_project(True), "paging.knxproj")
    b = srv.list_group_addresses(limit=4, cursor="1/3/2")
    assert [g["address"] for g in a["group_addresses"]] == [g["address"] for g in b["group_addresses"]], (a, b)

    srv._STATE["project"] = None
    print("test_paging: OK — group addresses and devices sort numerically and identically "
          "regardless of parser order; cursor paging covers every row exactly once; "
          "total_matched makes truncation explicit.")


if __name__ == "__main__":
    main()
