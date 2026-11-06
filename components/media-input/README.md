# Shared RoyVa image and video input

The existing Qwen3.6-35B-A3B Q8_0 endpoint now loads its matching F16 vision
projector. Model input capabilities include text, image and video. Text requests
retain the existing model and sampling; no cloud model or routing layer is added.
OpenCode's installed binary and pinned upstream checkout are unchanged.

The shared session prompt hook handles native API/CLI attachments and web/desktop
staged uploads (`metadata.attachments`). Images use native image admission. Video
is decoded into at most eight chronological JPEG frames, each labelled with its
timestamp. The prompt explicitly describes sparse sampling and the lack of audio.
Video limit: 20 MB and ten minutes. Supported input forms: data URI, local file
URI and stored `media:` reference. Temporary decoded video/frame files are deleted
after admission. Native session storage retains admitted image frames as normal.
Eight images maximum per request; a video can be combined with images only when
the total image/frame count stays within eight.

Telegram forwards photo messages, image/video documents, video messages and video
notes with their captions. Attachment-only messages receive a default description
request. Replies and steering preserve the attachments. Voice/audio transcription
continues on its existing path; video audio is not transcribed.

Projector provenance: `unsloth/Qwen3.6-35B-A3B-GGUF`, revision
`a483e9e6cbd595906af30beda3187c2663a1118c`, `mmproj-F16.gguf` (899283680 bytes).
SHA256: `8971ee4f331ff0a4c609374f32984b3d4e6dc086c0aa35f1d637fad1829e887f`.
Local path: `~/llm-server/models/mmproj-Qwen3.6-F16.gguf`. The launcher uses
`--image-min-tokens 1024` per llama.cpp's Qwen-VL image-resolution recommendation.
No model weights or credentials belong in Git.

Validation sources: `index.test.js` covers video decoding/order, staged UI uploads,
limits, Telegram attachment selection and native queued/steered file admission.
`telegram/media-routing.fixture.mjs` mocks external Telegram/native transport.
Additional live tests may use the real model/native API while mocking Telegram;
keep their fixtures/results private and do not imply that a real Telegram upload
was tested when its transport was mocked.
