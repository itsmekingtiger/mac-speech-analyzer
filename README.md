# mac-speech-analyzer

🐍 Python package to run the macOS 26 SpeechAnalyzer API from Python to transcribe audio files.

The SpeechAnalyzer API generally provides [faster and better results]((https://get-inscribe.com/blog/apple-speech-api-benchmark.html)) than other locally running transcription engines of comparable size. 

## Features

- **On-device transcription**. Audio never leaves your Mac.
- **Supports many languages**. Automatic model download on first use.
- **Progressive output**. Observe segments as they're finalized, or wait for the full transcript.

## Requirements

- macOS >= 26.0
- XCode command-line tools

## Installation

```bash
uv add mac-speech-analyzer
# or
pip install mac-speech-analyzer
```

## Usage

### Basic usage

```py
from macspeechanalyzer import transcribe

text = transcribe("/path/to/file", locale="en")
```

### Progressive transcription

`transcribe` returns the full transcript once analysis completes, but you can also observe segments as they're finalized. Pass any callable as on_segment and it'll be invoked once per segment, in order, with the segment text:

```py
from macspeechanalyzer import transcribe

# default: no progressive output
text = transcribe("/path/to/file", locale="en")

# echo each segment to stdout as it's transcribed
text = transcribe("/path/to/file", locale="en", on_segment=print)

# or use your own callback
def log(segment: str) -> None:
    print(f"... {segment} ...")

text = transcribe("/path/to/file", locale="en", on_segment=log)
```

Segments are non-overlapping and never revised, so appending them yields the same string as the return value.

### Segment timestamps

Pass `timestamps=True` to return a `TranscriptionResult` with the full text
and a list of `TranscriptionSegment` objects:

```py
from macspeechanalyzer import transcribe

result = transcribe("/path/to/file", locale="en", timestamps=True)
print(result.text)
for segment in result.segments:
    print(f"[{segment.start:.2f}s – {segment.end:.2f}s] {segment.text}")
```

`start` and `end` are seconds from the beginning of the audio file, using
the audio range reported by SpeechAnalyzer for each finalized segment.
These are segment-level timestamps. The segment texts concatenate to
`result.text`; audio with no recognized speech returns `text=""` and
`segments=[]`. Both result types can also be imported from `macspeechanalyzer`.

The default `timestamps=False` returns a string as before. You can combine
timestamps with `on_segment`; the callback continues to receive plain text.

## Technical details

This package is made up of two parts: the Python wrapper provides the API, but the actual functionality is achieved by embedding a Swift project which exposes functions to C. With this kind of three language interplay, a clean separation of concerns is really important. Therefore, the implementation is divided into the following four layers:

- Pure Python
- Python → C compat
- Swift → C compat
- Pure Swift

The pure Swift and pure Python layers only deal with their respective languages & types, while the compat layers do all the ugly work of converting between native and C-compatible types

## Roadmap

- ✅ Basic one-shot transcription
- Class-based interface
    - Context manager implementation
- Transcription of live audio stream (microphone, ...)


## Development

```zsh
uv pip install -e .
```

to one-time-install the package as editable, from then on:

```zsh
ninja
```

to rebuild the package

# License

mac-speech-analyzer is released under the MIT License. See [LICENSE](./LICENSE) for more details.
