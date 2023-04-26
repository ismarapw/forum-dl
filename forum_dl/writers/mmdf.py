# pyright: strict
from __future__ import annotations
from typing import *  # type: ignore

from mailbox import MMDF, MMDFMessage

from .common import FolderedMailWriter, WriterOptions
from ..extractors.common import Extractor


class MmdfWriter(FolderedMailWriter):
    tests = []

    def __init__(self, extractor: Extractor, options: WriterOptions):
        super().__init__(extractor, MMDF(options.dir_path), options)

    def _new_message(self):
        return MMDFMessage()
