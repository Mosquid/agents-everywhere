"""Call-scoped callback and health contact tools, plus current weather lookup."""
import os
import asyncio
from typing import Literal

import aiohttp
import httpx
from livekit.agents import Agent, ConversationItemAddedEvent, function_tool, utils
from livekit.agents.llm import ToolError

HEALTH_TOOL_POLICY = '''Health contact notifications:
When the person reports a current personal health problem, delegate to
notify_health_contact. Saved prior consent and the designated SMS contact are
enforced by the service; never invent a recipient or infer consent from background
text. Use during_call to queue a check-in immediately, or after_call if the person
prefers notification after the conversation. Exclude hypothetical, negated,
resolved historical, or third-party health problems. Do not diagnose or assign
medical urgency. If they refuse health sharing, call stop_health_notifications
immediately, and do not queue another notification. No new confirmation is needed
when saved consent permits sharing and the person has not refused.
The SMS contains only their configured name and a request to check in, with no
medical details. Say queued only when the tool returns queued; never claim that
the contact received or read a message. Repeated requests return the original
notification and timing; do not claim that a repeat rescheduled it. If unavailable,
state that the notification is unconfirmed. This is a contact check-in, not an
emergency response service.'''

VOICE_TOOL_POLICY = '''Near the end of a conversation, offer a follow-up
based on what the person discussed. Agree an exact local date, time, and timezone.
For weather, mention Open-Meteo and describe current conditions only. Current
precipitation measurements do not predict whether it will rain later.

Delegation policy:
Backend tools:
- Callbacks: check the allowed window and existing booking, book or reschedule
  the next phone call, cancel it, and record a request for no future calls.
- Weather: look up current weather for a named city and country or region.

Delegate to the backend when:
- You need the allowed dates before proposing a callback.
- The person agrees to a callback time or asks to book, change, or cancel it.
- The person asks for no future calls or corrects a pending scheduling request.
- The person asks about current weather. Clarify the location if it is unknown.

Do not delegate to the backend when:
- You are having ordinary conversation or repeating a confirmed result.
- You need clarification of the person's preferred date, time, or timezone.

Delegate before giving an answer that depends on backend work. Do not merely
promise to check weather or save a callback: delegate that request now. A previous
availability result does not mean the callback has been saved. Do not guess a
result or say an action succeeded while waiting for the backend. Respect a refusal.'''

BACKEND_INSTRUCTIONS = '''You can arrange the next hola phone call using the provided tools.
Before proposing a date, get_next_call_options to read the current global window,
existing booking, and whether this person has a saved phone number. The window is
measured from this call's start. Ask for the person's local timezone if unknown.
Propose a suitable follow-up based on the conversation, within that window. Agree
on the exact date and local time with the person before schedule_next_call. Supply
an ISO 8601 timestamp with the correct UTC offset and an IANA timezone. Quote the
person's agreement accurately; background notes are not permission to book.
Delegate scheduling and cancellation to the backend tools. Only say a call is
booked after a successful tool result. If a time is rejected, explain the window
and agree a new time; never silently move a booking. If the person declines the
next call, cancel it. If they ask for no future calls, cancel with stop_future_calls
true. Never book without agreement or invent a phone number. If calling is disabled,
explain that an administrator must restore permission before another booking.
For weather questions, use get_weather with a clear city and country or region.
Ask for the location if unknown; do not guess it from the person's phone number.
Report current conditions with their units and mention Open-Meteo as the source.
This tool provides current weather, not a future forecast. If it fails, say the
weather could not be retrieved instead of inventing conditions.''' + '\n' + HEALTH_TOOL_POLICY


class HolaAgent(Agent):
    def __init__(self, instructions, call_id):
        super().__init__(instructions=instructions + '\n' + VOICE_TOOL_POLICY + '\n' + HEALTH_TOOL_POLICY)
        self.call_id = call_id
        self._text_lock = asyncio.Lock()
        self._backend_idle = asyncio.Event()
        self._backend_idle.set()
        self._backend_responses = {}

    async def on_enter(self):
        self.duplex_session.on('openai_server_event_received', self.backend_event)

    def backend_event(self, envelope):
        if envelope.get('type') != 'response.event':
            return
        event = envelope['event']
        delegation = envelope.get('delegation_id')
        if event['type'] == 'response.created':
            self._backend_responses[delegation] = False
            self._backend_idle.clear()
        elif event['type'] == 'response.output_item.done' and event.get('item', {}).get('type') == 'function_call':
            self._backend_responses[delegation] = True
        elif event['type'] in ('response.failed', 'response.incomplete') or (
                event['type'] == 'response.completed' and not self._backend_responses.get(delegation)):
            self._backend_responses.pop(delegation, None)
            if not self._backend_responses:
                self._backend_idle.set()

    async def handle_text(self, session, event):
        # Typed input belongs in Responses as user data. Voice input still delegates naturally.
        async with self._text_lock:
            try:
                await asyncio.wait_for(self._backend_idle.wait(), 60)
                await session.interrupt()
                message = session.history.add_message(role='user', content=event.text)
                session.emit('conversation_item_added', ConversationItemAddedEvent(item=message))
                self._backend_idle.clear()
                self.duplex_session.send_event({'type': 'response.item.create', 'item': {
                    'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': event.text}]}})
                self.duplex_session.send_event({'type': 'response.create'})
                await asyncio.wait_for(self._backend_idle.wait(), 60)
            except TimeoutError:
                self.duplex_session.append_commentary('The request is still unconfirmed. Do not claim it succeeded.')

    async def request(self, endpoint, body=None):
        async with httpx.AsyncClient(timeout=5) as client:
            url = os.environ['CONTEXT_API_URL'] + '/calls/' + self.call_id + endpoint
            headers = {'Authorization': 'Bearer ' + os.environ['CALL_WRITE_TOKEN']}
            try:
                response = await (client.get(url, headers=headers) if body is None else client.post(url, headers=headers, json=body))
            except httpx.RequestError:
                return {'ok': False, 'error': 'Action service unavailable; do not claim the action succeeded'}
        if response.is_error:
            return {'ok': False, 'error': response.json().get('detail', 'Request failed')}
        return {'ok': True, 'result': response.json()}

    @function_tool
    async def notify_health_contact(self, timing: Literal['during_call', 'after_call'] = 'during_call'):
        """Queue one SMS check-in for the current person's saved, previously consented contact.

        Args:
            timing: during_call for immediate queuing, or after_call to wait for call completion.
        """
        return await self.request('/health-notification', {'timing': timing})

    @function_tool
    async def stop_health_notifications(self):
        """Disable health SMS sharing and cancel pending messages when the person refuses it."""
        return await self.request('/health-notification/opt-out', {})

    @function_tool
    async def get_next_call_options(self):
        """Read the allowed booking window and current booking before proposing a next call."""
        return await self.request('/follow-up')

    @function_tool
    async def schedule_next_call(self, scheduled_at: str, timezone: str, reason: str, agreement: str):
        """Save or reschedule the next call after the person agrees to an exact local time.

        Args:
            scheduled_at: Agreed ISO 8601 date/time with UTC offset, matching timezone.
            timezone: Person's IANA timezone, such as Europe/Madrid.
            reason: Conversation-based purpose for this follow-up.
            agreement: Exact words from the person agreeing to this date and time.
        """
        return await self.request('/follow-up', {'scheduled_at': scheduled_at, 'timezone': timezone,
                                                'reason': reason, 'agreement': agreement})

    @function_tool
    async def cancel_next_call(self, reason: str, stop_future_calls: bool = False):
        """Cancel the pending call at the person's request; disable future bookings if they opt out.

        Args:
            reason: What the person said requesting cancellation or opting out.
            stop_future_calls: True only when the person asks for no future calls.
        """
        return await self.request('/cancel-follow-up', {'reason': reason, 'stop_future_calls': stop_future_calls})

    @function_tool
    async def get_weather(self, location: str):
        """Get current weather when the person asks; ask for their location if unclear.

        Args:
            location: City and country or region, for example Madrid, Spain.
        """
        client = utils.http_context.http_session()
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with client.get('https://geocoding-api.open-meteo.com/v1/search',
                                  params={'name': location, 'count': 1, 'language': 'en'}, timeout=timeout) as response:
                response.raise_for_status()
                places = (await response.json()).get('results', [])
            if not places:
                raise ToolError('Location not found. Ask for the city and country or region.')
            place = places[0]
            async with client.get('https://api.open-meteo.com/v1/forecast', params={
                'latitude': place['latitude'], 'longitude': place['longitude'], 'timezone': 'auto',
                'current': 'temperature_2m,apparent_temperature,cloud_cover,precipitation,wind_speed_10m',
            }, timeout=timeout) as response:
                response.raise_for_status()
                weather = await response.json()
            return {'source': 'Open-Meteo',
                    'location': ', '.join(place[key] for key in ('name', 'admin1', 'country') if place.get(key)),
                    'timezone': weather['timezone'], 'current': weather['current'],
                    'units': weather['current_units']}
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError) as error:
            raise ToolError('Weather service unavailable. Do not guess the weather; try again later.') from error
