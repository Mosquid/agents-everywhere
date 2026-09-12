"""Provision Orange trunks in the new stack; run by Compose at startup."""
import asyncio
import os
from livekit import api

async def main():
    async with api.LiveKitAPI() as lk:
        number = os.environ['ORANGE_FROM_NUMBER']
        inbound = next((x for x in (await lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())).items if x.name == 'orange-inbound'), None)
        if inbound is None:
            inbound = await lk.sip.create_inbound_trunk(api.CreateSIPInboundTrunkRequest(trunk=api.SIPInboundTrunkInfo(
                name='orange-inbound', numbers=[number], allowed_addresses=[os.environ['ORANGE_PROXY_ALLOWED_ADDRESS']])))
        outbound = next((x for x in (await lk.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())).items if x.name == 'orange-local-proxy'), None)
        if outbound is None:
            outbound = await lk.sip.create_outbound_trunk(api.CreateSIPOutboundTrunkRequest(trunk=api.SIPOutboundTrunkInfo(
                name='orange-local-proxy', address=os.environ['ORANGE_PROXY_ADDRESS'],
                transport=api.SIP_TRANSPORT_UDP, numbers=[number])))
        dispatch = next((x for x in (await lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())).items if x.name == 'orange-gpt-live'), None)
        if dispatch is None:
            dispatch = await lk.sip.create_dispatch_rule(api.CreateSIPDispatchRuleRequest(dispatch_rule=api.SIPDispatchRuleInfo(
                name='orange-gpt-live', trunk_ids=[inbound.sip_trunk_id],
                rule=api.SIPDispatchRule(dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix='orange-')))))
        print('Inbound:', inbound.sip_trunk_id)
        print('Outbound:', outbound.sip_trunk_id)
        print('Dispatch:', dispatch.sip_dispatch_rule_id)
        assert inbound.sip_trunk_id in dispatch.trunk_ids
        assert not dispatch.room_config.agents, 'Expected automatic unnamed agent dispatch'

asyncio.run(main())
