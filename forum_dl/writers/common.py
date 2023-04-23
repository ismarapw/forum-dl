# pyright: strict
from __future__ import annotations
from typing import *  # type: ignore

from abc import ABC, abstractmethod
from dataclasses import dataclass
from mailbox import Mailbox, Message
from html2text import html2text
from email.utils import formatdate
import os

from ..extractors.common import Extractor, Thread, Board, Post, PageState
from ..version import __version__


@dataclass
class WriterOptions:
    content_as_title: bool
    textify: bool


@dataclass(kw_only=True)
class WriterState:
    board_path: list[str] | None = None
    board_page: PageState | None = None
    thread_page: PageState | None = None


class Writer(ABC):
    tests: list[dict[str, Any]]

    def __init__(self, extractor: Extractor, path: str, options: WriterOptions):
        self._extractor = extractor
        self._path = path
        self._options = options
        self._initial_state = WriterState()

    def write(self, url: str):
        self.read_metadata()
        self.write_version()

        base_node = self._extractor.node_from_url(url)

        if isinstance(base_node, Board):
            self.write_board(base_node)
        elif isinstance(base_node, Thread):
            self.write_thread(base_node)

    @abstractmethod
    def read_metadata(self):
        pass

    @abstractmethod
    def write_version(self):
        pass

    def write_board(self, board: Board):
        if (
            self._initial_state.board_path is not None
            and board.path != self._initial_state.board_path
        ):
            return

        cur_board_state = None

        for thread in self._extractor.threads(board, self._initial_state.board_page):
            if cur_board_state != self._extractor.board_state:
                self.write_board_state(self._extractor.board_state)
                cur_board_state = self._extractor.board_state

            self.write_thread(thread)

        self.write_board_state(None)
        self._initial_state.board_page = None

        for _, subboard in self._extractor.subboards(board).items():
            self.write_board(subboard)

    @abstractmethod
    def write_board_state(self, state: PageState | None):
        pass

    def write_thread(self, thread: Thread):
        cur_thread_state = None

        for post in self._extractor.posts(thread, self._initial_state.thread_page):
            if cur_thread_state != self._extractor.thread_state:
                self.write_thread_state(self._extractor.thread_state)
                cur_thread_state = self._extractor.thread_state

            self.write_post(thread, post)

        self.write_thread_state(None)
        self._initial_state.thread_page = None

    @abstractmethod
    def write_thread_state(self, state: PageState | None):
        pass

    @abstractmethod
    def write_post(self, thread: Thread, post: Post):
        pass


class SimulatedWriter(Writer):
    def read_metadata(self):
        pass

    def write_version(self):
        pass

    def write_board_state(self, state: PageState | None):
        pass

    def write_thread_state(self, state: PageState | None):
        pass

    def write_post(self, thread: Thread, post: Post):
        pass


class FilesystemWriter(Writer):
    def __init__(self, extractor: Extractor, path: str, options: WriterOptions):
        super().__init__(extractor, path, options)
        self._file: IO[str] | None = None

        os.makedirs(self._path, exist_ok=True)

    def __del__(self):
        if self._file:
            self._file.close()

    def read_metadata(self):
        pass  # TODO

    def write_version(self):
        pass  # TODO

    def write_board(self, board: Board):
        fspath = self._extractor.fspath(board)

        if fspath:
            os.makedirs(os.path.join(self._path, fspath), exist_ok=True)

        super().write_board(board)

    def write_board_state(self, state: PageState | None):
        pass  # TODO

    def write_thread(self, thread: Thread):
        fspath = self._extractor.fspath(thread)
        os.makedirs(os.path.join(self._path, os.path.dirname(fspath)), exist_ok=True)

        self._file = open(os.path.join(self._path, self._extractor.fspath(thread)), "w")
        super().write_thread(thread)
        self._file.close()

    def write_thread_state(self, state: PageState | None):
        pass  # TODO

    def write_post(self, thread: Thread, post: Post):
        if self._file:
            self._file.write(f"{self._serialize_post(post)}\n")

    @abstractmethod
    def _serialize_post(self, post: Post) -> str:
        pass


class MailWriter(Writer):
    def __init__(
        self,
        extractor: Extractor,
        path: str,
        mailbox: Mailbox[Any],
        options: WriterOptions,
    ):
        super().__init__(extractor, path, options)
        self._mailbox = mailbox

        for key, msg in self._mailbox.iteritems():
            if msg.get("X-Forumdl-Version"):
                self._metadata_key = key
        else:
            msg = self._new_message()
            self._metadata_key = self._mailbox.add(msg)

    def __del__(self):
        self._mailbox.flush()
        self._mailbox.close()

    def write(self, url: str):
        self._mailbox.lock()
        super().write(url)
        self._mailbox.unlock()

    def read_metadata(self):
        metadata = self._mailbox[self._metadata_key]
        self._initial_state = WriterState(
            board_path=metadata.get("X-Forumdl-Board-Path"),
            board_page=metadata.get("X-Forumdl-Board-Page"),
            thread_page=metadata.get("X-Forumdl-Thread-Page"),
        )

    def write_version(self):
        metadata = self._mailbox[self._metadata_key]

        del metadata["X-Forumdl-Version"]
        metadata["X-Forumdl-Version"] = __version__

        del metadata["Subject"]
        metadata["Subject"] = "[FORUM-DL]"

        metadata.set_type("text/plain")
        metadata.set_payload("[forum-dl]")

        self._mailbox[self._metadata_key] = metadata

    def write_board_state(self, state: PageState | None):
        metadata = self._mailbox[self._metadata_key]

        del metadata["X-Forumdl-Board-Page"]

        if state:
            metadata["X-Forumdl-Board-Page"] = str(state)

        self._mailbox[self._metadata_key] = metadata

    def write_thread_state(self, state: PageState | None):
        metadata = self._mailbox[self._metadata_key]

        del metadata["X-Forumdl-Thread-Page"]

        if state:
            metadata["X-Forumdl-Thread-Page"] = str(state)

        self._mailbox[self._metadata_key] = metadata

    def write_post(self, thread: Thread, post: Post):
        self._mailbox.add(self._build_message(thread, post))

    @abstractmethod
    def _new_message(self) -> Message:
        pass

    def _build_message(self, thread: Thread, post: Post):
        msg = self._new_message()

        msg["Message-ID"] = "<" + ".".join(post.path) + ">"
        msg["From"] = post.username

        if len(post.path) >= 2:
            msg["In-Reply-To"] = f"<{'.'.join(post.path[:-1])}>"

            refs = f"{post.path[0]}"
            for ref in post.path[1:-1]:
                refs += f" <{ref}>"

        if len(post.path) >= 2 and self._options.content_as_title:
            msg["Subject"] = html2text(post.content[:98]).partition("\n")[0]
        else:
            msg["Subject"] = thread.title

        msg["Date"] = formatdate(post.date)

        for prop_name, prop_val in post.properties.items():
            msg[f"X-Forumdl-Property-{prop_name.capitalize()}"] = str(prop_val)

        if self._options.textify:
            msg.set_type("text/plain")
            msg.set_payload(html2text(post.content), "utf-8")
        else:
            msg.set_type("text/html")
            msg.set_payload(post.content, "utf-8")

        return msg


class FolderedMailWriter(MailWriter):
    def __init__(
        self,
        extractor: Extractor,
        path: str,
        mailbox: Mailbox[Any],
        options: WriterOptions,
    ):
        super().__init__(extractor, path, mailbox, options)
        self.folders: dict[str, Mailbox[Any]] = {}

    def _folder_name(self, board: Board):
        return ".".join(board.path)

    def write_board(self, board: Board):
        folder_name = self._folder_name(board)
        self.folders[folder_name] = getattr(self._mailbox, "add_folder")(folder_name)
        super().write_board(board)

    def write_post(self, thread: Thread, post: Post):
        board = self._extractor.find_board(thread.path[:-1])
        folder_name = self._folder_name(board)
        self.folders[folder_name].add(self._build_message(thread, post))
