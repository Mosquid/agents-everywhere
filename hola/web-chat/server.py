import asyncio
import json
import os
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
from aiohttp import ClientSession, ClientTimeout, ClientError, web
from livekit import api

ROOT = Path(__file__).parent

async def page(request):
    return web.FileResponse(ROOT / 'index.html')

async def sdk(request):
    return web.FileResponse(ROOT / 'sdk.js')

async def load_identities():
    try:
        async with ClientSession(timeout=ClientTimeout(total=5)) as client:
            async with client.get(os.environ['CONTEXT_API_URL'] + '/people', headers={
                'Authorization': 'Bearer ' + os.environ['CONTEXT_ADMIN_TOKEN']
            }) as response:
                response.raise_for_status()
                people = await response.json()
    except (ClientError, asyncio.TimeoutError):
        raise web.HTTPServiceUnavailable(text='Cannot load saved identities')
    items = []
    for person in people:
        key = person.get('external_key') or ''
        if not key.startswith('rtc:') or not person.get('initial_data'):
            continue
        try:
            profile = json.loads(person['initial_data'])
        except (ValueError, TypeError):
            profile = {}
        if not isinstance(profile, dict):
            profile = {}
        items.append({'id': person['id'], 'identity': key[4:],
                      'name': profile.get('name') or key[4:], 'language': profile.get('language', '')})
    return items

async def identities(request):
    items = await load_identities()
    return web.json_response([{'id': p['id'], 'name': p['name'], 'language': p['language']} for p in items], headers={'Cache-Control': 'no-store'})

async def token(request):
    if request.headers.get('Origin') not in {'http://localhost:8092', 'http://127.0.0.1:8092'}:
        raise web.HTTPForbidden()
    body = await request.json()
    person_id = body.get('person_id')
    identity = 'chat-tester'
    if person_id:
        person = next((p for p in await load_identities() if p['id'] == person_id), None)
        if person is None:
            raise web.HTTPBadRequest(text='Selected identity no longer exists')
        identity = person['identity']
    room = 'chat-test-' + uuid4().hex[:12]
    jwt = (api.AccessToken(os.environ['LIVEKIT_API_KEY'], os.environ['LIVEKIT_API_SECRET'])
           .with_identity(identity).with_ttl(timedelta(minutes=30))
           .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_publish_data=True, can_subscribe=True)).to_jwt())
    return web.json_response({'url': os.environ['LIVEKIT_PUBLIC_URL'], 'token': jwt, 'room': room}, headers={'Cache-Control': 'no-store'})

app = web.Application()
app.add_routes([web.get('/', page), web.get('/sdk.js', sdk), web.post('/token', token), web.get('/identities', identities)])
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8092, access_log=None)
