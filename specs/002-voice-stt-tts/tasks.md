# Tasks — 002 voice input and spoken replies

## Implementation

- [x] Add `app/speech/stt.py`: multipart and JSON `input_audio` Whisper clients.
- [x] Add `app/speech/tts.py`: local Piper (OpenAI-compatible), Edge and ElevenLabs.
- [x] Add `app/telegram/voice.py`: bounded voice/audio download.
- [x] Register voice/audio intake before the text handler.
- [x] Keep group trigger parity for voice notes and captions.
- [x] Add `tts_mode` to conversations (schema v4, default `auto`).
- [x] Add `/tts off|all|auto` and `audio replies` in `/status`.
- [x] Send spoken answers as Telegram audio after the text answer.
- [x] Add `TTS_VOICE` and `TTS_VOICE_AUDIO`.
- [x] Route explicit audio requests through `/api/session/{id}/generate`.
- [x] Filter capability disclaimers and defer display until filtering.
- [x] Retry empty transient generations and use a short fallback.
- [x] Wire the sandbox to the shared `stt` (faster-whisper) and `tts` (Piper)
      services, replacing `opencode-stt` and Edge TTS.
- [x] Document the environment in `.env.example` and `README.md`.

## Verification

- [x] `155 passed`; `ruff` clean.
- [x] Real Edge TTS synthesis inside the bot container.
- [x] Real `opencode-stt` transcription inside the bot container.
- [x] Telegram `sendAudio` delivery to the private chat.
- [x] Explicit audio request produces English text and uses
      `en-US-AriaNeural`.
- [x] Default reply uses `es-ES-ElviraNeural`.
- [x] Schema v4 migration applied to the existing volume.
- [x] Bot health `ok` after redeploy.
