---
title: UGBS Service Navigator API
emoji: 🎓
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# UGBS Service Navigator — API

The backend for an OMIS 404 student project: a conversational assistant for
University of Ghana Business School administrative procedures. The web interface
is hosted separately and calls this service.

- `GET /health` — status and provider
- `POST /chat/stream` — one conversational turn, streamed as server-sent events
- `GET /analytics` — the administrative dashboard's data

Answers come from published University documents and a hand-checked procedure
catalogue. Five procedures were written by the project team because no published
version exists; they are labelled synthetic wherever they are cited.
