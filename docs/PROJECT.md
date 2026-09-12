# hola: project vision

A social network for older adults, built around ordinary phone calls.

The goal is to reduce loneliness by helping people stay involved in each other's
lives: hearing how a friend is doing, celebrating a grandchild's news, and knowing
someone will call. The intended experience requires no app, screen, or typing
from the person receiving a call.

The planned AI calls people to hear about their day and share news, stories, and
everyday gossip from their friends and family. With their permission, it would
pass their updates along to others in their circle. If a conversation raises
concerns about someone's wellbeing, the intended system could alert designated
relatives or escalate to appropriate support services.

## Current prototype

The implemented stack supports Orange telephone integration, AI conversation,
saved person profiles, one shared system prompt, and person-linked audio and
transcripts. It generates and stores post-call summaries, agrees the next call
based on the conversation, and automatically dials saved callbacks through
Orange. Global minimum and maximum delays are editable in hours (48–168 by
default, measured from the current call's start). Cancellation and future-call
opt-out are supported. A web chat interface exercises the same agent locally.
The agent can also retrieve current weather for a requested location.

Automatic sharing between people, sharing permissions, profile updates from
conversations, loading earlier conversations as memory, and wellbeing escalation
are not implemented. Summaries remain separate from the person's saved profile.
The shared prompt introduces hola and offers to arrange a follow-up. Saving a
recording or summary does not grant permission to share it.

For setup and the current operating limits, start with the
[root README](../README.md). The product vision above describes the intended
experience rather than a claim that those workflows are available today.
