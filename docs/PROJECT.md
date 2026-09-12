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

Evaluation of the hola.world project — a working voice agent that connects an elderly person with their social circle and support services through an ordinary telephone.

What proved decisive for us was the complete end-to-end scenario shown live during the presentation. The team demonstrated a real phone call, a conversation with the agent, the sharing of social posts, and an escalation to social services. The key parts of the product worked one after another, within a single user flow.

We identified several technical and product characteristics that determined our choice.

1. Working integration with real telephony

The demonstration began with a phone call and continued as a voice conversation with the agent. This showed that the entire chain works: establishing the connection, transmitting speech, processing the conversation, and responding by voice.

For this project, that is fundamental: an ordinary telephone serves as a fully-fledged interface for accessing the system. The user doesn't need to install an app, type queries, or navigate multiple screens. The engineering complexity stays inside the product, while the interaction keeps the familiar form of a conversation.

2. From understanding speech to taking action

During the demo, the agent both took part in the conversation and carried out the operations tied to it. The outcome of the dialogue was used to share social posts and, in the relevant scenario, to escalate to social services.

It is precisely this transition that matters technically:
User's speech → understanding the situation → choosing an action → executing the operation → a result beyond the conversation itself.

The team showed that the voice interface is connected to applied functionality. The user could address the system in natural language and, through conversation, obtain a concrete result.

3. Social functionality between participants

The presentation showed social posts being shared. This confirmed that the interaction goes beyond a single conversation between a person and an AI and supports communication within a social circle.

Here voice input, the content of the post, and its delivery to other participants come together. For the user, this means being able to share their life and stay included in the life of their community through a channel available to them.

We value this characteristic in particular: the project's central benefit arises in the connection between people, which the agent helps sustain.

4. Escalation was part of the working scenario

The team demonstrated the transition from conversation to escalation to social services. In doing so, an external operation related to obtaining support was included in the demonstrated process.

This is a significant level of integration: the system must link the content of the conversation to a subsequent request and pass it through the designated channel. The escalation shown confirmed that this process can be initiated directly from a phone conversation.

For the person, the value lies in shortening the path from a problem described to a request for help. Further handling of the request remains with the receiving service.

5. Autonomous continuation of the interaction

Another important characteristic of hola.world is that the agent independently schedules the date of the next call. This complements the demonstrated cycle with the ability to arrange the next contact.

This gives the system useful autonomy: the agent takes on the organization of continued communication. The person doesn't have to initiate a new conversation or set a reminder each time.

6. Completeness of several integrations in one product

The team's most convincing technical achievement is the joint operation of telephony, the voice agent, social functionality, and external escalation. The presentation demonstrated a path through these components from real input to the system's follow-up actions.

It is for this combination that we awarded the win to hola.world: the team showed a technically coherent product with clear value for a specific audience. Through a familiar telephone, a person gains the ability to communicate, participate in the life of their circle, and reach out for support. The agent makes these capabilities available in an environment the user already knows how to use.
