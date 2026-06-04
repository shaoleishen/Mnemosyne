#!/usr/bin/env python3
"""Merge retry results into the main Vision API output."""

import re
from pathlib import Path


def extract_page_content(md_text: str, page_num: int) -> str | None:
    """Extract content for a specific page from markdown."""
    pattern = rf'<!-- Page {page_num} -->\n\n(.*?)(?=<!-- Page \d+ -->|$)'
    match = re.search(pattern, md_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def main():
    base_dir = Path(__file__).parent

    # Read main output
    main_file = base_dir / "science.adz2742_vision.md"
    with open(main_file, "r", encoding="utf-8") as f:
        main_content = f.read()

    # Failed pages to retry
    failed_pages = [3, 8, 20, 21, 22]

    # Read retry files
    retry_files = {
        3: base_dir / "science.adz2742_vision_retry.md",
        8: base_dir / "science.adz2742_vision_retry8.md",
        20: base_dir / "science.adz2742_vision_retry20.md",
        21: base_dir / "science.adz2742_vision_retry20.md",
        22: base_dir / "science.adz2742_vision_retry20.md",
    }

    # Replace failed pages with retry content
    for page_num in failed_pages:
        retry_file = retry_files[page_num]
        if retry_file.exists():
            with open(retry_file, "r", encoding="utf-8") as f:
                retry_content = f.read()

            # Extract the page content from retry
            page_content = extract_page_content(retry_content, page_num)
            if page_content:
                # Replace the error comment with the actual content
                error_pattern = rf'<!-- Page {page_num} — ERROR: .*? -->'
                replacement = f'<!-- Page {page_num} -->\n\n{page_content}'
                main_content = re.sub(error_pattern, lambda m: replacement, main_content, count=1)
                print(f"✅ Replaced Page {page_num}")
            else:
                print(f"⚠️  No content found for Page {page_num} in {retry_file}")
        else:
            print(f"❌ Retry file not found: {retry_file}")

    # Write the merged output
    output_file = base_dir / "science.adz2742_vision_final.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(main_content)

    print(f"\n✅ Merged output written to: {output_file}")
    print(f"   Total size: {len(main_content):,} characters")


if __name__ == "__main__":
    main()
