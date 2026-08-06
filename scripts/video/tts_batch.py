#!/usr/bin/env python3
"""
Convert Insight InSAR narration Markdown to MP3 via edge-tts.

Usage:
  python scripts/video/tts_batch.py docs/video/narration-full.md
  python scripts/video/tts_batch.py docs/video/narration-full.md --split-by-heading
  python scripts/video/tts_batch.py --list-voices
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
SKIP_HEADING_KEYWORDS = ("录制备注", "不读出来", "可选片尾", "文件说明", "README")

# Stable ASCII slugs for known Chinese section titles (Windows-safe filenames)
HEADING_SLUG_MAP = {
    "片头": "00-opening",
    "第一部分 系统介绍与运行环境": "01-intro",
    "第一部分": "01-intro",
    "第二部分 软件安装": "02-install",
    "第二部分": "02-install",
    "第三部分 软件使用": "03-usage",
    "第三部分": "03-usage",
    "结尾": "99-closing",
    "第1页 视频封面": "slide-01-cover",
    "第2页 软件设计理念": "slide-02-philosophy",
    "第3页 总体架构": "slide-03-architecture",
    "第4页 WSL介绍": "slide-04-wsl",
    "第5页 ISCE2介绍": "slide-05-isce2",
    "第6页 MintPy介绍": "slide-06-mintpy",
    "第7页 完整处理链路": "slide-07-workflow",
}


def heading_to_slug(title: str) -> str:
    t = title.strip()
    if t in HEADING_SLUG_MAP:
        return HEADING_SLUG_MAP[t]
    for key, slug in HEADING_SLUG_MAP.items():
        if key in t:
            return slug
    slug = re.sub(r"[^\w]+", "-", t, flags=re.ASCII).strip("-").lower()
    return slug or "section"


def strip_markdown_for_tts(text: str) -> str:
    """Remove elements unsuitable for straight TTS reading."""
    lines: list[str] = []
    in_code = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r"^#{1,6}\s", line):
            # Drop markdown headings; keep spoken flow from paragraphs only
            continue
        if line.strip() in ("---", "***", "___"):
            continue
        if line.strip().startswith("|"):
            continue
        if line.strip().startswith(">"):
            line = line.lstrip("> ").strip()
        line = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        if line.strip().startswith("- [") or line.strip().startswith("* ["):
            continue
        if line.strip().startswith("- ") and ":" in line[:40]:
            # bullet with label — keep text after first colon if looks like prose
            pass
        lines.append(line)

    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def should_skip_section(title: str) -> bool:
    t = title.lower()
    return any(k in title for k in SKIP_HEADING_KEYWORDS) or t.startswith("model id")


def split_by_h2(md: str) -> list[tuple[str, str]]:
    """Return (slug, plain_text) per ## section."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    parts: list[tuple[str, str]] = []
    current_title = "full"
    current_lines: list[str] = []

    for line in md.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                text = strip_markdown_for_tts("\n".join(current_lines))
                if text and not should_skip_section(current_title):
                    parts.append((heading_to_slug(current_title), text))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = strip_markdown_for_tts("\n".join(current_lines))
        if text and not should_skip_section(current_title):
            parts.append((heading_to_slug(current_title), text))

    return parts if parts else [("full", strip_markdown_for_tts(md))]


async def synthesize(text: str, out_path: Path, voice: str, rate: str) -> None:
    import edge_tts

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
            await communicate.save(str(out_path))
            return
        except Exception as exc:
            last_error = exc
            if out_path.exists():
                out_path.unlink()
            if attempt < 3:
                print(f"Retrying {out_path.name} ({attempt}/3): {exc}")
                await asyncio.sleep(2 * attempt)
    assert last_error is not None
    raise last_error


async def list_zh_voices() -> None:
    import edge_tts

    voices = await edge_tts.list_voices()
    for v in sorted(voices, key=lambda x: x["ShortName"]):
        if v.get("Locale", "").startswith("zh"):
            print(f"{v['ShortName']}\t{v.get('Gender', '')}\t{v.get('FriendlyName', '')}")


async def run_batch(
    sections: list[tuple[str, str]],
    out_dir: Path,
    voice: str,
    rate: str,
    prefix: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (slug, text) in enumerate(sections, start=1):
        if len(text) < 2:
            continue
        name = f"{prefix}{i:02d}-{slug}.mp3" if len(sections) > 1 else f"{prefix}{slug}.mp3"
        out_path = out_dir / name
        if out_path.is_file() and out_path.stat().st_size > 0:
            print(f"Skipping existing {out_path}")
            continue
        print(f"Generating {out_path} ({len(text)} chars)...")
        await synthesize(text, out_path, voice, rate)
    print(f"Done. {len(sections)} file(s) in {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown narration → MP3 (edge-tts)")
    parser.add_argument("markdown", nargs="?", type=Path, help="Path to narration .md")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("docs/video/audio"))
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", default=DEFAULT_RATE)
    parser.add_argument(
        "--split-by-heading",
        action="store_true",
        help="One MP3 per ## section (skips meta sections)",
    )
    parser.add_argument("--prefix", default="", help="Output filename prefix")
    parser.add_argument("--list-voices", action="store_true", help="List zh-* Edge TTS voices")
    args = parser.parse_args()

    if args.list_voices:
        asyncio.run(list_zh_voices())
        return 0

    if not args.markdown or not args.markdown.is_file():
        parser.error("markdown file required (or use --list-voices)")

    md = args.markdown.read_text(encoding="utf-8")
    if args.split_by_heading:
        sections = split_by_h2(md)
    else:
        plain = strip_markdown_for_tts(md)
        stem = args.markdown.stem
        sections = [(stem, plain)]

    if not sections or all(not t for _, t in sections):
        print("No speakable text found after stripping markdown.", file=sys.stderr)
        return 1

    asyncio.run(run_batch(sections, args.output_dir, args.voice, args.rate, args.prefix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
