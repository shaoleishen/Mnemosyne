"""Prompts for the RAG flow.

These prompts enforce the evidence contract:
- Physical text, captions, and original screenshots are evidence
- Machine-extracted tables and VLM descriptions are auxiliary interpretation only
"""

from __future__ import annotations

# System prompt for the RAG generator
RAG_SYSTEM_PROMPT = """You are a scientific evidence assistant. Your task is to answer questions based on the provided evidence from scientific papers.

## Evidence Contract

You MUST follow these rules strictly:

1. **Physical Evidence** (highest trust):
   - PDF physical text (body text extracted directly from the PDF)
   - Physical captions (captions physically present in the PDF near figures/tables)
   - Original screenshots (figures/tables extracted directly from the PDF)

2. **Auxiliary Interpretation** (lower trust, use for context only):
   - Machine-extracted table Markdown (tables converted from screenshots by Vision API)
   - VLM descriptions (AI-generated descriptions of figures/tables)

## Rules

- Use PDF physical text, physical captions, and original screenshots as your primary evidence.
- Use machine-extracted tables and VLM descriptions only as auxiliary interpretation.
- If auxiliary text conflicts with physical sources, ALWAYS trust the physical sources.
- When answering, identify whether each cited support is:
  - Physical text
  - Physical caption
  - Original media (figure/table screenshot)
  - Machine table extraction
  - Auxiliary interpretation (VLM description)

## Citation Format

When citing evidence, use this format:
- For physical text: [Source: Physical Text, Paper: {title}, Page: {page}]
- For captions: [Source: Physical Caption, Figure/Table: {label}]
- For original media: [Source: Original Media, Figure/Table: {label}]
- For machine tables: [Source: Machine Extraction (auxiliary), Table: {label}]
- For VLM descriptions: [Source: VLM Description (auxiliary), Figure/Table: {label}]
"""


def format_multimodal_prompt(
    query: str,
    context_texts: list[dict],
    context_media: list[dict],
    auxiliary_context: list[dict],
) -> list[dict]:
    """Format a multimodal prompt with explicit source sections.

    Args:
        query: User's question
        context_texts: Physical text evidence
        context_media: Original media assets
        auxiliary_context: Machine-extracted tables and VLM descriptions

    Returns:
        List of message dicts for the chat API
    """
    content_parts = []

    # Add physical text evidence
    if context_texts:
        content_parts.append({
            "type": "text",
            "text": "## Physical Text Evidence\n\n"
        })
        for i, chunk in enumerate(context_texts, 1):
            title = chunk.get("title", "Unknown")
            page = chunk.get("page_start", "?")
            section = chunk.get("section", "")
            text = chunk.get("text", "")

            content_parts.append({
                "type": "text",
                "text": f"### Source {i}: {title} (Page {page})\n"
                        f"Section: {section}\n\n"
                        f"{text}\n\n"
            })

    # Add original media (images)
    if context_media:
        content_parts.append({
            "type": "text",
            "text": "## Original Figures/Tables\n\n"
        })
        for i, media in enumerate(context_media, 1):
            label = media.get("figure_label", f"Figure/Table {i}")
            caption = media.get("caption_text", "")
            image_path = media.get("image_path", "")

            content_parts.append({
                "type": "text",
                "text": f"### {label}\n"
                        f"Caption: {caption}\n\n"
            })

            # Add image if available
            if image_path:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"file://{image_path}"},
                })

    # Add auxiliary context
    if auxiliary_context:
        content_parts.append({
            "type": "text",
            "text": "\n## Auxiliary Interpretation (Machine-Generated)\n\n"
                    "**Note: The following are machine-generated interpretations. "
                    "Use only as supplementary context. If they conflict with physical evidence above, "
                    "trust the physical evidence.**\n\n"
        })
        for i, aux in enumerate(auxiliary_context, 1):
            source_type = aux.get("source_type", "unknown")
            label = aux.get("figure_label", f"Item {i}")
            text = aux.get("text", aux.get("description_text", ""))

            content_parts.append({
                "type": "text",
                "text": f"### {label} ({source_type})\n\n"
                        f"{text}\n\n"
            })

    # Add the query
    content_parts.append({
        "type": "text",
        "text": f"\n## Question\n\n{query}\n\n"
                "Please answer based on the evidence above. "
                "Cite your sources using the specified format."
    })

    return [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": content_parts},
    ]


def format_text_only_prompt(
    query: str,
    context_texts: list[dict],
) -> list[dict]:
    """Format a text-only prompt when no media is available.

    Args:
        query: User's question
        context_texts: Physical text evidence

    Returns:
        List of message dicts for the chat API
    """
    content_parts = []

    if context_texts:
        content_parts.append({
            "type": "text",
            "text": "## Evidence\n\n"
        })
        for i, chunk in enumerate(context_texts, 1):
            title = chunk.get("title", "Unknown")
            page = chunk.get("page_start", "?")
            section = chunk.get("section", "")
            text = chunk.get("text", "")

            content_parts.append({
                "type": "text",
                "text": f"### Source {i}: {title} (Page {page})\n"
                        f"Section: {section}\n\n"
                        f"{text}\n\n"
            })

    content_parts.append({
        "type": "text",
        "text": f"\n## Question\n\n{query}\n\n"
                "Please answer based on the evidence above. Cite your sources."
    })

    return [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": content_parts},
    ]
