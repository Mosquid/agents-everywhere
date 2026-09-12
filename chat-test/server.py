from pathlib import Path
from datetime import timedelta
from uuid import uuid4
from aiohttp import web
from livekit import api

ROOT = Path(__file__).parent
ENV = dict(line.split('=', 1) for line in (ROOT.parent / 'livekit' / '.env').read_text().splitlines() if '=' in line)

async def page(request):
    return web.FileResponse(ROOT / 'index.html')

async def sdk(request):
    return web.FileResponse(ROOT / 'node_modules/livekit-client/dist/livekit-client.umd.js')

async def token(request):
    if request.headers.get('Origin') not in {'http://localhost:8092', 'http://127.0.0.1:8092'}:
        raise web.HTTPForbidden()
    room = 'chat-test-' + uuid4().hex[:12]
    jwt = (api.AccessToken(ENV['LIVEKIT_API_KEY'], ENV['LIVEKIT_API_SECRET'])
           .with_identity('chat-tester').with_ttl(timedelta(minutes=30))
           .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_publish_data=True, can_subscribe=True)).to_jwt())
    return web.json_response({'url': 'ws://192.168.1.195:7880', 'token': jwt, 'room': room}, headers={'Cache-Control': 'no-store'})

app = web.Application()
app.add_routes([web.get('/', page), web.get('/sdk.js', sdk), web.post('/token', token)])
web.run_app(app, host='127.0.0.1', port=8092, access_log=None)
