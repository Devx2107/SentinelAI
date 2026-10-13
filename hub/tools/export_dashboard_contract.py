"""Export reproducible API responses for frontend runtime-guard tests."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard_dev import create_app


def export():
    paths={'health':'/health','overview':'/overview','devices':'/devices','deviceDetail':'/devices/hub',
        'events':'/events?limit=2','summary':'/events/summary','cards':'/rfid/cards','activity':'/rfid/activity?limit=2',
        'entryStats':'/entry-monitor/stats','system':'/system','insights':'/insights'}
    with TemporaryDirectory() as folder:
        app=create_app(Path(folder)/'fixture.db',clock=lambda:datetime(2026,10,13,12,tzinfo=timezone.utc))
        app.config.update(DASHBOARD_USER='admin',DASHBOARD_PASSWORD='dev')
        client=app.test_client()
        auth={'Authorization':'Basic '+base64.b64encode(b'admin:dev').decode()}
        result={name:client.get('/api/v1'+path,headers=auth).json for name,path in paths.items()}
        result.update(event=result['events']['events'][0],device=result['devices']['devices'][0],card=result['cards']['cards'][0],error=client.get('/api/v1/overview').json)
    target=Path(__file__).resolve().parents[2]/'dashboard-ui/src/api/schema/fixtures.json'
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': export()
