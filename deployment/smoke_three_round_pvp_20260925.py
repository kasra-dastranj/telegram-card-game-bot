"""Read-only-to-live-service staging smoke test using an isolated temporary DB."""
import os
from pathlib import Path
import sys
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='telbattle-three-smoke-') as scratch:
    os.environ['DATABASE_PATH'] = str(Path(scratch) / 'game.db')
    from core.models import Card, CardRarity
    import web.miniapp_api as app_module

    app_module.app.config.update(TESTING=True, DEBUG=True)
    client = app_module.app.test_client()
    database = app_module.db
    for user_id, card_id in ((101, 'smoke-one'), (202, 'smoke-two')):
        database.get_or_create_player(user_id)
        card = Card(card_id=card_id, name=card_id, rarity=CardRarity.NORMAL,
                    power=80, speed=70, iq=60, popularity=50,
                    abilities=[], card_type='POWER_TYPE')
        assert database.add_card(card)
        assert database.add_card_to_player(user_id, card_id)

    def post(path, user_id, payload=None):
        response = client.post(path, json=payload or {}, headers={'X-Debug-User-Id': str(user_id)})
        assert response.status_code in (200, 201), (path, response.status_code, response.get_json())
        return response.get_json()

    first = post('/api/v1/three-round/matchmaking', 101)
    second = post('/api/v1/three-round/matchmaking', 202)
    assert second['phase'] == 'card_selection'
    request_id = first['request_id']
    post('/api/v1/three-round/matches/' + request_id + '/card', 101, {'card_id': 'smoke-one'})
    post('/api/v1/three-round/matches/' + request_id + '/card', 202, {'card_id': 'smoke-two'})
    for stat in ('power', 'speed', 'iq'):
        post('/api/v1/three-round/matches/' + request_id + '/stat', 101, {'stat': stat})
        result = post('/api/v1/three-round/matches/' + request_id + '/stat', 202, {'stat': stat})
    assert result['status'] == 'completed'
    assert result['report']['is_tie']
    assert len(result['report']['rounds']) == 3
    print('Staged Python 3.9 three-round smoke passed')
