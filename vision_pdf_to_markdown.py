#!/usr/bin/env python3
"""
PDF → Markdown via Vision API (MiMo V2 Omni)
Reads PDF pages as images, sends to Vision API, outputs structured Markdown.
"""

import os
import sys
import json
import time
import base64
import argparse
from pathlib import Path

import fitz  # PyMuPDF
import requests


def load_env(env_path: str = ".env"):
    """Load .env file into os.environ."""
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def pdf_page_to_image_bytes(page, dpi: int = 300) -> bytes:
    """Render a PDF page to PNG bytes at given DPI."""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def call_vision_api(
    image_b64: str,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int = 4096,
) -> str:
    """Send image + prompt to Vision API, return text response."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    },
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Extract content — handle reasoning_content fallback
    choice = data["choices"][0]["message"]
    content = choice.get("content") or ""
    if not content:
        content = choice.get("reasoning_content") or ""
    return content.strip()


PROMPT_SINGLE = """You are a scientific document OCR and layout engine.
Convert the following page from a scientific paper into well-structured Markdown.

Rules:
- Preserve all headings, paragraphs, lists, tables, and figure captions.
- For tables, use GitHub-flavored Markdown table syntax.
- Preserve math notation using LaTeX ($...$ for inline, $$...$$ for display).
- Preserve figure/table captions exactly as printed.
- Do NOT hallucinate or add content not present in the image.
- Output ONLY the Markdown content, no preamble or explanation."""


PROMPT_CONTINUATION = """You are a scientific document OCR and layout engine.
Convert the following page from a scientific paper into well-structured Markdown.
This is page {page_num} of a continuing document. Maintain consistency with prior context.

Rules:
- Preserve all headings, paragraphs, lists, tables, and figure captions.
- For tables, use GitHub-flavored Markdown table syntax.
- Preserve math notation using LaTeX ($...$ for inline, $$...$$ for display).
- Preserve figure/table captions exactly as printed.
- Do NOT hallucinate or add content not present in the image.
- Output ONLY the Markdown content, no preamble or explanation."""


def process_pdf(
    pdf_path: str,
    output_path: str,
    api_key: str,
    base_url: str,
    model: str,
    dpi: int = 300,
    max_tokens: int = 4096,
    start_page: int = 0,
    end_page: int | None = None,
    delay: float = 1.0,
):
    """Process entire PDF page by page, write Markdown output."""
    doc = fitz.open(pdf_path)
    total = len(doc)
    if end_page is None:
        end_page = total
    end_page = min(end_page, total)

    print(f"📄 PDF: {pdf_path}")
    print(f"   Pages: {total}, processing [{start_page}..{end_page})")
    print(f"   Model: {model}, DPI: {dpi}")
    print(f"   Output: {output_path}")
    print()

    all_markdown = []
    all_markdown.append(f"# {Path(pdf_path).stem}\n\n")
    all_markdown.append(f"*Processed via Vision API ({model}) — {time.strftime('%Y-%m-%d %H:%M')}*\n\n---\n\n")

    for i in range(start_page, end_page):
        page = doc[i]
        print(f"  📖 Page {i+1}/{total}...", end=" ", flush=True)

        # Render page to image
        img_bytes = pdf_page_to_image_bytes(page, dpi=dpi)
        img_b64 = image_to_base64(img_bytes)

        # Choose prompt
        if i == start_page:
            prompt = PROMPT_SINGLE
        else:
            prompt = PROMPT_CONTINUATION.format(page_num=i + 1)

        # Call Vision API
        try:
            t0 = time.time()
            md = call_vision_api(img_b64, prompt, api_key, base_url, model, max_tokens)
            elapsed = time.time() - t0
            print(f"✅ {len(md)} chars ({elapsed:.1f}s)")
            all_markdown.append(f"<!-- Page {i+1} -->\n\n{md}\n\n")
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP {e.response.status_code}: {e.response.text[:200]}")
            all_markdown.append(f"<!-- Page {i+1} — ERROR: {e} -->\n\n")
        except Exception as e:
            print(f"❌ Error: {e}")
            all_markdown.append(f"<!-- Page {i+1} — ERROR: {e} -->\n\n")

        # Rate limit delay
        if i < end_page - 1:
            time.sleep(delay)

    doc.close()

    # Write output
    output = "\n".join(all_markdown)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n✅ Done! Output written to: {output_path}")
    print(f"   Total size: {len(output):,} characters")
    return output


def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown via Vision API")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("-o", "--output", help="Output Markdown file path")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI (default: 300)")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens per page")
    parser.add_argument("--start", type=int, default=0, help="Start page (0-indexed)")
    parser.add_argument("--end", type=int, default=None, help="End page (0-indexed, exclusive)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls (seconds)")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    args = parser.parse_args()

    # Load env
    env_path = args.env
    if not os.path.isabs(env_path):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), env_path)
    load_env(env_path)

    api_key = os.environ.get("VISION_API_KEY")
    base_url = os.environ.get("VISION_API_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("VISION_MODEL", "mimo-v2-omni")

    if not api_key:
        print("❌ VISION_API_KEY not set in environment or .env")
        sys.exit(1)

    # Default output path
    if not args.output:
        stem = Path(args.pdf).stem
        args.output = str(Path(args.pdf).parent / f"{stem}_vision.md")

    process_pdf(
        pdf_path=args.pdf,
        output_path=args.output,
        api_key=api_key,
        base_url=base_url,
        model=model,
        dpi=args.dpi,
        max_tokens=args.max_tokens,
        start_page=args.start,
        end_page=args.end,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
