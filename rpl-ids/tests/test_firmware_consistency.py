"""Cross-check firmware DET/ALERT records against the Python reference model.

Uses the kept evidence logs so the test is deterministic and needs no Cooja.
For every (monitor, window) the NBR records give the counts; the model must
reproduce the DET line (n, mean, sigma, k, threshold) exactly and the same
set of ALERT lines.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ids_model as m  # noqa: E402
import parse_logs as p  # noqa: E402

LOGS = sorted((ROOT / "report" / "evidence").glob("section[34]*.log"))


@pytest.mark.parametrize("log", LOGS, ids=[l.name for l in LOGS])
def test_det_and_alerts_match_model(log):
    t = p.parse(log)
    nbr, det, alert = t["NBR"], t["DET"], t["ALERT"]
    assert len(det) > 0, "no DET records in evidence log"
    dis_thr = int(t["IDS"].iloc[0]["dis_thr"])
    checked = 0
    for (mote, win), g in nbr.groupby(["mote", "win"]):
        d = det[(det.mote == mote) & (det.win == win)]
        assert len(d) == 1, (mote, win)
        d = d.iloc[0]
        g = g.sort_values("nbr")
        counts = g.dio.astype(int).tolist()
        ids = g.nbr.astype(int).tolist()
        n, mean, sigma, k, thr = m.profile(counts)
        assert (n, mean, sigma, k, thr) == (int(d.n), int(d.mean_x1000), int(d.sigma_x1000),
                                            int(d.k_x1000), int(d.thr_x1000)), (mote, win, counts)
        a = alert[(alert.mote == mote) & (alert.win == win)]
        got_dio = sorted(a[a.kind == "DIO"].nbr.astype(int).tolist())
        got_dis = sorted(a[a.kind == "DIS"].nbr.astype(int).tolist())
        exp_dio = sorted(ids[i] for i in m.dio_alerts(counts))
        exp_dis = sorted(ids[i] for i in m.dis_alerts(g.dis.astype(int).tolist(), dis_thr))
        assert got_dio == exp_dio and got_dis == exp_dis, (mote, win)
        checked += 1
    assert checked > 0
