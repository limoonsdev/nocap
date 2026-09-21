"""Local audio solver (reCAPTCHA/hCaptcha fallback) via SpeechRecognition."""
from __future__ import annotations
import io, time
from .base import BaseSolver, SolverContext, SolverResult

class AudioSolver(BaseSolver):
    name = "audio"
    method = "SpeechRecognition (free Google / offline Sphinx)"
    notes = "Downloads the audio, transcribes locally when possible."

    async def solve_bytes(self, raw: bytes) -> SolverResult:
        t0 = time.time()
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(raw); path = f.name
            try:
                with sr.AudioFile(path) as src:
                    audio = r.record(src)
                try:
                    text = r.recognize_sphinx(audio)  # offline
                    backend = "sphinx"
                except Exception:
                    text = r.recognize_google(audio, language="fr-FR")
                    backend = "google"
                ms = int((time.time() - t0) * 1000)
                return SolverResult(ok=True, text=text, confidence=0.7, detail={"backend": backend}, ms=ms)
            finally:
                os.unlink(path)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": str(e)}, ms=int((time.time()-t0)*1000))

    async def solve(self, ctx: SolverContext) -> SolverResult:
        return SolverResult(ok=False, detail={"error": "use POST /v1/solve/audio"}, ms=0)
