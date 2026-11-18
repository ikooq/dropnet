from dropnet import site,store
from tests.test_ftc_load import R
from dropnet.ftc import load
import json


def test_date_quality_export_preserves_flags(tmp_path):
    path=tmp_path/'db.rl'; conn=store.open_store(path)
    first=R(1,'2178637210',day='2026-10-15'); first.violation_day='2026-10-16'
    second=R(2,'2178637210',day='2026-10-15'); second.violation_day=''
    load.load_reports(conn,[first,second]);conn.close()
    out=tmp_path/'dates.json'; site.export_date_quality(path,out)
    data=json.loads(out.read_text(encoding='utf-8')); x=data['issues'][first.number]
    assert data['reports']==2 and x['call_after_filing']==1 and x['missing']==1
    assert x['examples'][0]['reported_call_date']=='2026-10-16'
