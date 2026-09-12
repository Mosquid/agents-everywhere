import asyncio
import json
import shlex
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
from aiohttp import web
from livekit import api

ROOT = Path(__file__).parent
ENV = dict(line.split('=', 1) for line in (ROOT.parent / 'hola' / '.env').read_text().splitlines() if '=' in line)

async def page(request):
    return web.FileResponse(ROOT / 'index.html')

async def sdk(request):
    return web.FileResponse(ROOT / 'node_modules/livekit-client/dist/livekit-client.umd.js')

async def load_identities():
    # Keep database credentials and profile contents on the existing server.
    script = """
import json,os,urllib.request
request=urllib.request.Request('http://127.0.0.1:8090/people',headers={'Authorization':'Bearer '+os.environ['CONTEXT_ADMIN_TOKEN']})
people=json.load(urllib.request.urlopen(request,timeout=5))
items=[]
for p in people:
    key=p.get('external_key') or ''
    if not key.startswith('rtc:') or not p.get('initial_data'):
        continue
    try:
        profile=json.loads(p['initial_data'])
    except (ValueError,TypeError):
        profile={}
    if not isinstance(profile,dict):
        profile={}
    items.append({'id':p['id'],'identity':key[4:],'name':profile.get('name') or key[4:],'language':profile.get('language','')})
print(json.dumps(items))
"""
    command = 'cd /home/inlanger/stacks/gpt-live && docker compose exec -T context-api python -c ' + shlex.quote(script)
    process = await asyncio.create_subprocess_exec('ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '192.168.1.195', command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=12)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise web.HTTPServiceUnavailable(text='Identity service timed out')
    if process.returncode:
        raise web.HTTPServiceUnavailable(text='Cannot load saved identities')
    return json.loads(output)

async def identities(request):
    items = await load_identities()
    return web.json_response([{'id':p['id'],'name':p['name'],'language':p['language']} for p in items], headers={'Cache-Control':'no-store'})

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
    jwt = (api.AccessToken(ENV['LIVEKIT_API_KEY'], ENV['LIVEKIT_API_SECRET'])
           .with_identity(identity).with_ttl(timedelta(minutes=30))
           .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_publish_data=True, can_subscribe=True)).to_jwt())
    return web.json_response({'url': 'ws://192.168.1.195:7880', 'token': jwt, 'room': room}, headers={'Cache-Control': 'no-store'})

app = web.Application()
app.add_routes([web.get('/', page), web.get('/sdk.js', sdk), web.post('/token', token), web.get('/identities', identities)])
web.run_app(app, host='127.0.0.1', port=8092, access_log=None)
