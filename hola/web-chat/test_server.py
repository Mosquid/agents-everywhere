import base64
import json
import os
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import server


class WebChatTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fail_api = False
        async def people(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer private-admin-token')
            if self.fail_api:
                raise web.HTTPServiceUnavailable()
            return web.json_response([
                {'id': 'person-1', 'external_key': 'rtc:demo-person', 'phone': '+12025550123',
                 'initial_data': json.dumps({'name': 'Test Person', 'language': 'English', 'private_note': 'not for browser'})},
                {'id': 'no-profile', 'external_key': 'rtc:unknown', 'initial_data': None},
            ])
        api_app = web.Application()
        api_app.router.add_get('/people', people)
        self.api = TestServer(api_app)
        await self.api.start_server()
        self.env = patch.dict(os.environ, {
            'CONTEXT_API_URL': str(self.api.make_url('')).rstrip('/'),
            'CONTEXT_ADMIN_TOKEN': 'private-admin-token',
            'LIVEKIT_PUBLIC_URL': 'ws://localhost:7880',
            'LIVEKIT_API_KEY': 'local-key', 'LIVEKIT_API_SECRET': 's' * 32,
        })
        self.env.start()
        app = web.Application()
        app.router.add_get('/identities', server.identities)
        app.router.add_post('/token', server.token)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.api.close()
        self.env.stop()

    async def test_direct_profile_lookup_and_selected_token(self):
        response = await self.client.get('/identities')
        self.assertEqual(await response.json(), [{'id': 'person-1', 'name': 'Test Person', 'language': 'English'}])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response = await self.client.post('/token', json={'person_id': 'person-1'}, headers={'Origin': 'http://localhost:8092'})
        result = await response.json()
        self.assertEqual(result['url'], 'ws://localhost:7880')
        payload = result['token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        self.assertEqual(claims['sub'], 'demo-person')

    async def test_invalid_origin_and_unknown_person(self):
        response = await self.client.post('/token', json={}, headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(response.status, 403)
        response = await self.client.post('/token', json={'person_id': 'missing'}, headers={'Origin': 'http://localhost:8092'})
        self.assertEqual(response.status, 400)

    async def test_context_failure_is_reported(self):
        self.fail_api = True
        response = await self.client.get('/identities')
        self.assertEqual(response.status, 503)
