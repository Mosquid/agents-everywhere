import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from livekit.agents.llm import ChatContext, ToolError
from agent_tools import HolaAgent, utils


class WeatherTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_tools_bind_current_call_and_cannot_select_a_recipient(self):
        agent = HolaAgent('Test', 'current-call')
        with patch.object(agent, 'request', AsyncMock(return_value={'ok': True, 'result': {'status': 'queued'}})) as request:
            result = await agent.notify_health_contact('after_call')
            request.assert_awaited_once_with('/health-notification', {'timing': 'after_call'})
            self.assertEqual(result['result']['status'], 'queued')
            await agent.stop_health_notifications()
            request.assert_awaited_with('/health-notification/opt-out', {})

    async def test_typed_messages_reach_backend_in_order_and_are_recorded(self):
        backend = MagicMock()
        class TestAgent(HolaAgent):
            @property
            def duplex_session(self):
                return backend
        agent = TestAgent('Test', 'test-call')
        session = MagicMock(history=ChatContext.empty(), interrupt=AsyncMock())
        sent = asyncio.Queue()
        def send(event):
            if event['type'] == 'response.create':
                agent.backend_event({'type': 'response.event', 'delegation_id': None, 'event': {'type': 'response.created'}})
                sent.put_nowait(True)
        backend.send_event.side_effect = send
        first = asyncio.create_task(agent.handle_text(session, SimpleNamespace(text='Check the weather')))
        await asyncio.wait_for(sent.get(), 1)
        second = asyncio.create_task(agent.handle_text(session, SimpleNamespace(text='Call me Wednesday')))
        for kind, item in [('response.output_item.done', {'type': 'function_call'}), ('response.completed', {})]:
            agent.backend_event({'type': 'response.event', 'delegation_id': None, 'event': {'type': kind, 'item': item}})
        self.assertFalse(agent._backend_idle.is_set())
        for kind in ('response.created', 'response.completed'):
            agent.backend_event({'type': 'response.event', 'delegation_id': None, 'event': {'type': kind}})
        await asyncio.wait_for(sent.get(), 1)
        agent.backend_event({'type': 'response.event', 'delegation_id': None, 'event': {'type': 'response.completed'}})
        await asyncio.gather(first, second)
        inputs = [call.args[0]['item'] for call in backend.send_event.call_args_list if call.args[0]['type'] == 'response.item.create']
        self.assertEqual([item['content'][0]['text'] for item in inputs], ['Check the weather', 'Call me Wednesday'])
        self.assertTrue(all(item['role'] == 'user' for item in inputs))
        self.assertEqual([item.text_content for item in session.history.items], ['Check the weather', 'Call me Wednesday'])
        self.assertEqual(session.emit.call_count, 2)

    async def test_weather_result_and_provider_failures(self):
        place = {'name': 'Madrid', 'admin1': 'Madrid', 'country': 'Spain',
                 'latitude': 40.42, 'longitude': -3.7}
        weather = {'timezone': 'Europe/Madrid', 'current': {'time': '2026-09-12T15:00', 'temperature_2m': 24},
                   'current_units': {'temperature_2m': '°C'}}
        cases = [('success', [{'results': [place]}, weather], None),
                 ('unknown place', [{}], None),
                 ('unavailable', [{}], aiohttp.ClientError('offline')),
                 ('malformed weather', [{'results': [place]}, {}], None)]
        for name, payloads, failure in cases:
            with self.subTest(name=name):
                client = MagicMock()
                responses = []
                for payload in payloads:
                    response = MagicMock()
                    response.__aenter__.return_value = response
                    response.json = AsyncMock(return_value=payload)
                    response.raise_for_status.side_effect = failure
                    responses.append(response)
                client.get.side_effect = responses
                with patch.object(utils.http_context, 'http_session', return_value=client):
                    agent = HolaAgent('Test', 'test-call')
                    if name == 'success':
                        result = await agent.get_weather('Madrid, Spain')
                        self.assertEqual(result['current'], weather['current'])
                        self.assertEqual(result['units'], weather['current_units'])
                        self.assertEqual(result['source'], 'Open-Meteo')
                        self.assertIn('Spain', result['location'])
                    else:
                        with self.assertRaises(ToolError):
                            await agent.get_weather('Madrid, Spain')
