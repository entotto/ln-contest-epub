from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
import typing as t
from pathlib import Path
from string import Template
from urllib.parse import urlparse

import httpx
#import readabilipy
import yaml
from ebooklib import epub
from ebooklib.utils import parse_string
from jinja2 import Environment, PackageLoader, select_autoescape
from lxml import etree
from pydantic import BaseModel, validator

build_dir = Path("build")
jinja_env = Environment(
    loader=PackageLoader(__name__),
    autoescape=select_autoescape()
)
book_yaml = "book.yaml"


class Entry(BaseModel):
    title: str
    emoji_url: str
    emoji_name: str
    tags: t.List[str]
    url: str

    @validator("tags", pre=True)
    def split_tags(cls, v):
        if isinstance(v, str):
            return re.split(r"\s*,\s*", v)
        return v

    @property
    def basename(self) -> str:
        safe_characters = ("_", "-")
        return "".join(c for c in re.sub(r"\s+", "-", self.title.lower()) if c.isalnum() or c in safe_characters).rstrip()

    @property
    def google_drive_file_id(self) -> str:
        url_parts = urlparse(self.url)
        assert url_parts.hostname == "docs.google.com"
        path = Path(url_parts.path)
        if path.name == "edit":
            path = path.parent
        return path.name

    @property
    def chapter_title(self) -> str:
        return f":{self.emoji_name}: {self.title}"

    @property
    def metadata_target(self) -> Path:
        return (build_dir / self.basename).with_suffix(".yaml")

    @property
    def raw_html_target(self) -> Path:
        return (build_dir / self.basename).with_suffix(".raw.html")

    @property
    def readable_html_target(self) -> Path:
        return (build_dir / self.basename).with_suffix(".readable.html")

    @property
    def emoji_target(self) -> Path:
        emoji_url = urlparse(self.emoji_url)
        return (build_dir / self.emoji_name).with_suffix(Path(emoji_url.path).suffix)


class Book(BaseModel):
    title: str
    entries: t.List[Entry]

    @classmethod
    def from_yaml(cls, filename: str) -> Book:
        content = yaml.load(open(book_yaml), Loader=yaml.SafeLoader)
        entries = list(map(lambda x: Entry(**x), content["entries"]))
        return cls(title=content["title"], entries=entries)

    @property
    def identifier(self) -> str:
        m = hashlib.sha256()
        m.update(self.title.encode("utf8"))
        return m.hexdigest()

    @property
    def cover_html_target(self) -> Path:
        return build_dir / "cover.html"

    @property
    def cover_image_target(self) -> Path:
        return build_dir / "cover.png"

    @property
    def epub_target(self) -> Path:
        return build_dir / "book.epub"


book = Book.from_yaml(book_yaml)


def task_entries():
    def write_entries(targets):
        for entry in book.entries:
            entry.metadata_target.parent.mkdir(exist_ok=True)
            with open(entry.metadata_target, "w") as f:
                f.write(yaml.dump(entry.dict))

    return {
        "file_dep": [book_yaml],
        "targets": [entry.metadata_target for entry in book.entries],
        "actions": [write_entries]
    }


def task_raw_html():
    def make_download_html(entry: Entry):
        def download_html(targets):
            export_url = f"https://www.googleapis.com/drive/v3/files/{entry.google_drive_file_id}/export"
            response = httpx.get(export_url, params=dict(mimeType="text/html", key=os.environ["GOOGLE_API_KEY"]))
            with open(targets[0], "w") as f:
                f.write(response.text)
        return download_html


    for entry in book.entries:
        yield {
            "name": entry.basename,
            "file_dep": [entry.metadata_target],
            "targets": [entry.raw_html_target],
            "actions": [make_download_html(entry)],
        }


def task_emoji():
    def make_download_emoji(entry: Entry):
        def download_emoji(targets):
            response = httpx.get(entry.emoji_url)
            with open(targets[0], "wb") as f:
                f.write(response.content)
        return download_emoji

    for entry in book.entries:
        yield {
            "name": entry.basename,
            "file_dep": [entry.metadata_target],
            "targets": [entry.emoji_target],
            "actions": [make_download_emoji(entry)],
        }


def task_readable_html():
    def make_run_readability(entry: Entry):
        def run_readability(targets):
            with open(entry.raw_html_target) as f:
                readable = readabilipy.simple_json_from_html_string(f.read(), use_readability=False)
            with open(targets[0], "w") as f:
                f.write(readable["content"])
        return run_readability

    for entry in book.entries:
        yield {
            "name": entry.basename,
            "file_dep": [entry.raw_html_target],
            "targets": [entry.readable_html_target],
            "actions": [make_run_readability(entry)],
        }


def image_to_data_url(path: Path) -> str:
    prefix = f"data:image/{path.suffix[1:]};base64,"
    return prefix + base64.b64encode(path.read_bytes()).decode('utf-8')


def task_cover():
    def write_cover_html(targets):
        template = jinja_env.get_template("cover.jinja")
        context = {
            # From https://www.transparenttextures.com/
            "background_texture": image_to_data_url(Path("images/paper-fibers.png")),
            "title": book.title,
            "text_direction": "ltr",
        }
        with open(targets[0], "w") as f:
            f.write(template.render(**context))

    yield {
        "name": "html",
        "file_dep": [book_yaml, "templates/cover.jinja"],
        "targets": [book.cover_html_target],
        "actions": [write_cover_html]
    }

    def write_cover_image(targets):
        subprocess.run([
            "chromium",
            "--headless",
            f"--screenshot={targets[0]}",
            "--window-size=600,800",
            "--default-background-color=0",
            "--hide-scrollbars",
            book.cover_html_target,
        ])

    yield {
        "name": "image",
        "file_dep": [book.cover_html_target],
        "targets": [book.cover_image_target],
        "actions": [write_cover_image]
    }


class EpubCoverHtml(epub.EpubCoverHtml):
    """
    Custom cover item class that preserves styling.
    """
    def get_content(self) -> str:
        self.content = self.book.get_template('cover')

        # Don't let the parent class process content, as it'll strip away the style tag
        tree = parse_string(self.content)
        tree_root = tree.getroot()

        images = tree_root.xpath('//xhtml:img', namespaces={'xhtml': epub.NAMESPACES['XHTML']})

        images[0].set('src', self.image_name)
        images[0].set('alt', self.title)

        tree_str = etree.tostring(tree, pretty_print=True, encoding='utf-8', xml_declaration=True)

        return tree_str


def make_epub(output: str, book: Book):
    epub_book = epub.EpubBook()

    # set metadata
    epub_book.set_identifier(book.identifier)
    epub_book.set_title(book.title)
    epub_book.set_language('en')
    epub_book.add_author('Various Authors')

    epub_book.set_cover("cover.png", book.cover_image_target.read_bytes(), create_page=False)
    cover_page = EpubCoverHtml(image_name="cover.png")
    epub_book.add_item(cover_page)

    # create chapters
    chapter_template = jinja_env.get_template("chapter.jinja")
    chapters = []
    for i, entry in enumerate(book.entries):
        chapter_number = i + 1
        chapter = epub.EpubHtml(title=entry.chapter_title, file_name=f"chapter_{chapter_number:02}.xhtml", lang="en")

        emoji = epub.EpubImage()
        emoji.file_name = entry.emoji_target.name
        emoji.content = entry.emoji_target.read_bytes()
        epub_book.add_item(emoji)

        # Commented out as it may be better to preserve the original formatting at the expense of improved readability.
        #content = entry.readable_html_target.read_text()
        raw_html = entry.raw_html_target.read_text()
        raw_html_lower = raw_html.lower()
        chapter.content = chapter_template.render(
            raw_html=raw_html,
            title=entry.title,
            url=entry.url,
            tags=entry.tags,
            emoji_file_name=emoji.file_name,
            emoji_name=entry.emoji_name,
            raw_html_includes_title=entry.title.lower() in raw_html_lower,
            # Note: There's a chance of false positives if the author managed to weave in the tags in the main text
            raw_html_includes_tags=all((tag.lower() in raw_html_lower for tag in entry.tags)),
            raw_html_failed_to_export="cannotExportFile" in raw_html,
        )
        epub_book.add_item(chapter)
        chapters.append(chapter)

    epub_book.toc = chapters

    # add default NCX and Nav file
    epub_book.add_item(epub.EpubNcx())
    epub_book.add_item(epub.EpubNav())

    # define CSS style
    stylesheet = Path("stylesheets/style.css").read_text()
    style_item = epub.EpubItem(uid="style_nav", file_name="style.css", media_type="text/css", content=stylesheet)
    epub_book.add_item(style_item)

    # set spine
    epub_book.spine = [cover_page, 'nav'] + chapters

    # write to the file
    epub.write_epub(output, epub_book, {})


def task_epub():
    def write_epub(targets):
        return make_epub(targets[0], book)

    return {
        "file_dep": ([entry.raw_html_target for entry in book.entries]
                     + [entry.emoji_target for entry in book.entries]
                     + [book.cover_image_target, "stylesheets/style.css", "templates/chapter.jinja"]),
        "targets": [book.epub_target],
        "actions": [write_epub]
    }
