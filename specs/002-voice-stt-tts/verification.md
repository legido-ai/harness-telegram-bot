# Verification — 002 voice input and spoken replies

**Date**: 2026-11-07
**Commit under test**: `3ec6984` on `main`
**Deployment**: sandbox bot `@legido_opencode2_bot` (`otb-bot`)
**Status**: Validated

## Test suite

```text
$ .venv/bin/python -m pytest -q
159 passed, 1 warning

$ .venv/bin/python -m ruff check app tests
All checks passed!
```

The suite is offline: fake Telegram, fake OpenCode, fake STT/TTS. It covers
voice download, transcription, the text-only default, explicit audio requests,
TTS failure handling, mode changes and the capability-disclaimer filter.

The music app was verified separately:

```text
141 passed, 0 failed
```

## Live validation

| Scenario | Result |
|---|---|
| Voice note with default `/tts off` | Transcribed and answered in **text only**, no audio file |
| Explicit “genera un audio corto” | Phrase generated, text posted, local Piper audio sent |
| “responde en castellano” | Spanish text generated, `es-ES-ElviraNeural` voice |
| “responde en inglés” | English text generated, `en-US-AriaNeural` voice |
| Default voice | Spanish `es-ES-ElviraNeural` |
| Explicit-audio voice | English `en-US-AriaNeural` |
| Local speech round trip | `text-to-speech` MP3 → `speech-to-text` transcript |
| Schema | v5; both conversations `tts_mode=off` after migration |
| Bot health | `status=ok`, poller/SSE/agent healthy |
| Old `opencode` | untouched: dedicated `opencode-stt` + Edge TTS |
| Music | shared `speech-to-text`/`text-to-speech`; `/healthz` has `stt:true`, `tts:true` |

## Deployed topology

```text
opencode2 (otb-bot) ── deploy_default ──┐
                                        ├── speech-to-text  (faster-whisper)
music (music-net) ──────────────────────┤
                                        └── text-to-speech  (Piper)
opencode (old) ─────── box_default ─────── opencode-stt (dedicated) + Edge TTS
```

## Known limits

- The old `opencode` bridge keeps Edge TTS until it is recreated by the
  operator; this cycle deliberately did not touch it.
- Audio is text-only by default; `/tts auto` or `/tts all` must be enabled for
  automatic spoken answers.
- Real-time voice sessions are out of scope.
