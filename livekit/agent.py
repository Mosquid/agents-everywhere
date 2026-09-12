from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession
from livekit.plugins.openai.realtime import GPTLiveModel


server = AgentServer(host="127.0.0.1", port=8089)


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        llm=GPTLiveModel(model="gpt-live-1", voice="marin", delegation="client")
    )
    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions=(
                "You are a concise, friendly voice assistant for a conversation test. "
                "Reply in the user's language. Answer directly and keep replies short. "
                "No backend or tools are connected. Do not delegate or claim to take "
                "external actions. If asked for an action or information you cannot "
                "provide, briefly explain that limitation."
            )
        ),
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
