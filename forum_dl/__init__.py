import logging
import sys

from .forumdl import ForumDl
from . import options

from .session import SessionOptions
from .extractors.common import ExtractorOptions
from .writers.common import WriterOptions


def main():
    parser = options.build_parser()
    args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(args.loglevel)

    forumdl = ForumDl()

    if args.list_extractors:
        print("\n".join(forumdl.list_extractors()))
    elif not args.urls:
        parser.error(
            "The following arguments are required: URL\n"
            "Use 'forum-dl --help' to get a list of all options."
        )
    else:
        forumdl.download(
            urls=args.urls,
            output_format=args.output_format,
            path=args.output,
            session_options=SessionOptions(
                get_urls=args.get_urls,
            ),
            extractor_options=ExtractorOptions(
                path=args.path,
            ),
            writer_options=WriterOptions(
                content_as_title=args.content_as_title,
                textify=args.textify,
            ),
        )
