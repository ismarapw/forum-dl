# pyright: strict
from __future__ import annotations
from typing import *  # type: ignore

from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs
import bs4
import re

from .common import normalize_url
from .common import ForumExtractor, Board, Thread, Post
from ..cached_session import CachedSession


class InvisionForumExtractor(ForumExtractor):
    tests = []

    @staticmethod
    def detect(session: CachedSession, url: str):
        response = session.get(url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        breadcrumbs_ul = soup.find("ul", attrs={"data-role": "breadcrumbList"})
        breadcrumb_lis = breadcrumbs_ul.find_all("li")
        base_url = url

        if len(breadcrumb_lis) >= 2:
            base_url = breadcrumb_lis[1].find("a").get("href")

        if soup.find("a", attrs={"title": "Invision Community"}):
            return InvisionForumExtractor(session, base_url)

    def _fetch_top_boards(self):
        self.root.are_subboards_fetched = True

        response = self._session.get(self._base_url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        board_divs = soup.find_all("div", class_="cForumGrid")
        for board_div in board_divs:
            board_id = board_div.get("data-forumid")
            board_h3 = soup.find("h3", class_="cForumGrid__title")
            board_anchor = board_h3.find("a")

            self._set_board(
                path=[board_id],
                url=board_anchor.get("href"),
                title=board_anchor.string,
                are_subboards_fetched=True,
            )

    def _fetch_subboards(self, board: Board):
        if board is self.root:
            return

        response = self._session.get(board.url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        subboard_lis = soup.find_all("li", class_="cForumRow")
        for subboard_li in subboard_lis:
            subboard_id = subboard_li.get("data-forumID")
            subboard_h4 = soup.find("h4", class_="ipsDataItem_title")
            subboard_anchor = subboard_h4.find("a")

            self._set_board(
                path=board.path + [subboard_id],
                title=subboard_anchor.string,
                are_subboards_fetched=True,
            )

    def _get_node_from_url(self, url: str):
        response = self._session.get(url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        breadcrumbs_ul = soup.find("ul", attrs={"data-role": "breadcrumbList"})
        breadcrumb_lis = breadcrumbs_ul.find_all("li")

        if len(breadcrumb_lis) <= 2:
            return self.root

        # Thread.
        if soup.find("article"):
            board_href = breadcrumb_lis[-2].find("a").get("href")

            for cur_board in self._boards:
                if cur_board.url == board_href:
                    return cur_board
        # Board.
        else:
            for cur_board in self._boards:
                if cur_board.url == url:
                    return cur_board

        raise ValueError

    def _fetch_lazy_subboard(self, board: Board, id: str):
        pass

    def _fetch_lazy_subboards(self, board: Board):
        pass

    def _get_board_page_items(self, board: Board, page_url: str, cur_page: int = 1):
        if board == self.root:
            return None

        response = self._session.get(page_url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        thread_lis = soup.find_all(
            "li", attrs={"data-controller": "forums.front.forum.topicRow"}
        )
        for thread_li in thread_lis:
            thread_id = thread_li.get("data-rowid")
            thread_span = thread_li.find("span", class_="cTopicTitle")
            thread_anchor = thread_span.find("a")

            yield Thread(path=board.path + [thread_id], url=thread_anchor.get("href"))

        next_page_link = soup.find("link", attrs={"rel": "next"})
        if next_page_link:
            return (next_page_link.get("href"), cur_page + 1)

    def _get_thread_page_items(self, thread: Thread, page_url: str, cur_page: int = 1):
        response = self._session.get(page_url)
        soup = bs4.BeautifulSoup(response.content, "html.parser")

        content_divs = soup.find_all("div", attrs={"data-role": "commentContent"})
        for content_div in content_divs:
            yield Post(path=thread.path, content=str(content_div.encode_contents()))

        next_page_link = soup.find("link", attrs={"rel": "next"})
        if next_page_link:
            return (next_page_link.get("href"), cur_page + 1)
