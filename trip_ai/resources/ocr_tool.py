from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..ocr_paddle import OcrParsed, parse_with_paddle_layout_parsing


@dataclass(frozen=True)
class OcrTool:
    """
    Resource tool used by the Event Understanding agent.
    """

    settings: Settings

    def run(self, *, file_bytes: bytes, filename: str) -> OcrParsed:
        return parse_with_paddle_layout_parsing(settings=self.settings, file_bytes=file_bytes, filename=filename)

