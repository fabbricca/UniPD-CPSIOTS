"""Parser robustness (PROJECT_PLAN section 11: empty / incomplete records)."""
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import parse_logs as p  # noqa: E402


def test_empty_and_malformed_lines(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("\n\n"
                   "garbage\n"
                   "abc\t5\tSTAT\t1\n"                 # non-numeric time
                   "1000\t5\tSTAT\t256\t1\n"            # incomplete STAT
                   "2000\t5\tNBR\t0\t7\t3\n"            # incomplete NBR
                   "3000\t1\tRX\t4\t12\n"
                   "TEST OK\n")
    t = p.parse(log)
    assert len(t["STAT"]) == 1 and t["STAT"].iloc[0]["rank"] == 256
    assert math.isnan(t["STAT"].iloc[0]["parent_changes"])
    assert len(t["NBR"]) == 1 and len(t["RX"]) == 1
    assert t["RX"].iloc[0]["from"] == 4


def test_empty_file(tmp_path):
    log = tmp_path / "e.log"; log.write_text("")
    t = p.parse(log)
    assert all(len(df) == 0 for df in t.values())
