import ctypes
from dataclasses import dataclass
import json
from pathlib import Path
import logging
from typing import Callable, Literal, overload
import os

log = logging.getLogger(__name__)

LOG_CB = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
SEGMENT_CB = ctypes.CFUNCTYPE(None, ctypes.c_char_p)

@LOG_CB
def _log_cb(level, msg):
    # for now, hacky: newline and flush stdout before/after each log print, otherwise logs may be bolted straight to a segment
    print("", flush=True)
    log.log(level or logging.INFO, msg.decode("utf-8", "replace") if msg else "")

@SEGMENT_CB
def _live_cb(msg):
    print(msg.decode("utf-8", "replace") if msg else "", end="", flush=True)

_lib = ctypes.CDLL(str(Path(__file__).parent / f"libmacspeechanalyzer_core.dylib"))

# The segment callback and error output are scoped to this invocation.
_lib.msa_transcribe_v2.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
    SEGMENT_CB,
]
_lib.msa_transcribe_v2.restype = ctypes.c_int32

_lib.msa_transcribe_v3.argtypes = [
    *_lib.msa_transcribe_v2.argtypes, ctypes.c_int32,
]
_lib.msa_transcribe_v3.restype = ctypes.c_int32

# void msa_free_string(char* ptr)
_lib.msa_free_string.argtypes = [ctypes.c_void_p]
_lib.msa_free_string.restype = None

_lib.msa_set_log_callback.argtypes = [LOG_CB]
_lib.msa_set_log_callback.restype = None
_lib.msa_set_log_callback(_log_cb)

class SpeechAnalyzerError(Exception):
    pass

@dataclass(frozen=True)
class TranscriptionSegment:
    """Finalized text with start/end times in seconds from the audio's start."""

    text: str
    start: float
    end: float

@dataclass(frozen=True)
class TranscriptionResult:
    """Full transcript and its finalized segments, in audio order."""

    text: str
    segments: list[TranscriptionSegment]

def _take_string(ptr: ctypes.c_void_p) -> str:
    """Copy a Swift-allocated C string into a Python str, then free it."""
    try:
        return ctypes.string_at(ptr).decode("utf-8")
    finally:
        _lib.msa_free_string(ptr)

@overload
def transcribe(path: str | Path, locale: str | None = None, on_segment: Callable[[str], None] | None = None, *, timestamps: Literal[False] = False) -> str: ...

@overload
def transcribe(path: str | Path, locale: str | None = None, on_segment: Callable[[str], None] | None = None, *, timestamps: Literal[True]) -> TranscriptionResult: ...

@overload
def transcribe(path: str | Path, locale: str | None = None, on_segment: Callable[[str], None] | None = None, *, timestamps: bool) -> str | TranscriptionResult: ...

def transcribe(path: str | Path, locale: str | None = None, on_segment: Callable[[str], None] | None = None, *, timestamps: bool = False) -> str | TranscriptionResult:
    """Transcribe an audio file on-device.

    Runs synchronously and returns the full transcript once the file has
    been fully analyzed. If ``on_segment`` is provided, it is also invoked
    once per finalized segment as transcription progresses, allowing the
    caller to observe or display partial results without waiting for the
    final return value.

    Args:
        path: Filesystem path to the audio file to transcribe. Any format
            readable by ``AVAudioFile`` is accepted (e.g. wav, m4a, mp3,
            caf, aiff).
        locale: BCP 47 / Apple locale identifier (e.g. ``"en_US"``,
            ``"de_DE"``, ``"ja_JP"``) selecting the transcription language.
            If ``None``, the system's current locale is used when supported,
            otherwise English. If the requested locale's model is not yet
            installed on the device, it will be downloaded on first use.
        on_segment: Optional callback invoked from a background thread once
            per finalized transcript segment, in order, with the segment
            text as its single argument. Segments are non-overlapping and
            never revised, so appending them reconstructs the full
            transcript. Pass ``print`` to echo segments to stdout as they
            arrive.
        timestamps: If ``True``, return a ``TranscriptionResult`` containing
            the full text and finalized segments with ``start`` and ``end``
            times in seconds relative to the beginning of the audio file.
            These are segment-level times, not word-level times or wall-clock
            times. ``on_segment`` still receives only the segment text.

    Returns:
        The complete transcript as a single string by default, or a
        ``TranscriptionResult`` when ``timestamps=True``. Audio with no
        recognized speech yields empty text and an empty segment list.

    Raises:
        SpeechAnalyzerError: If the file cannot be read, the host is running
            a macOS version older than 26.0, or the native pipeline fails.
    """
    # Keep this CFUNCTYPE object alive until the native call has fully finished.
    cb = SEGMENT_CB()  # NULL callback
    if on_segment is print:
        cb = _live_cb
    elif on_segment is not None:
        def _trampoline(raw: bytes | None) -> None:
            if raw is not None:
                on_segment(raw.decode("utf-8", "replace"))
        cb = SEGMENT_CB(_trampoline)

    path = os.fspath(path)

    out = ctypes.c_void_p()
    error = ctypes.c_void_p()
    status = _lib.msa_transcribe_v3(
        path.encode("utf-8"),
        locale.encode("utf-8") if locale is not None else None,
        ctypes.byref(out),
        ctypes.byref(error),
        cb,
        int(timestamps),
    )
    if status != 0:
        msg = _take_string(error) if error.value else f"native error (status {status})"
        raise SpeechAnalyzerError(msg)
    if not out.value:
        raise SpeechAnalyzerError("transcribe returned success but no text")
    text = _take_string(out)
    if not timestamps:
        return text
    result = json.loads(text)
    return TranscriptionResult(
        text=result["text"],
        segments=[TranscriptionSegment(**segment) for segment in result["segments"]],
    )
