"""Prompts for Vision API tasks.

This module provides default prompts for:
- Figure/table description (describe_media)
- Table to Markdown extraction (table_to_markdown)
"""

from __future__ import annotations


# Default prompt for describing figures and tables
DESCRIBE_MEDIA_PROMPT = """Please describe this figure/table in detail.

Instructions:
1. Identify the type of visual (figure, chart, graph, table, diagram, etc.)
2. Describe the main content and key elements
3. For charts/graphs: describe axes, trends, key data points
4. For tables: describe the structure and key values
5. For figures: describe what is shown and any labels
6. Note any text, legends, or annotations visible

Provide a clear, concise description that would help someone understand the content without seeing the image."""


# Default prompt for extracting tables as Markdown
TABLE_TO_MARKDOWN_PROMPT = """Please extract the table from this image and convert it to Markdown format.

Instructions:
1. Preserve the table structure with proper Markdown syntax (| for columns, - for header separator)
2. Include all rows and columns visible in the image
3. If there are merged cells, represent them appropriately
4. Keep the original text content as accurately as possible
5. If there are mathematical expressions, use LaTeX notation ($...$)
6. Preserve the header row and separate it with the Markdown separator line

Output only the Markdown table, no additional text."""


# Task type to prompt mapping
_TASK_PROMPTS = {
    "describe_media": DESCRIBE_MEDIA_PROMPT,
    "table_to_markdown": TABLE_TO_MARKDOWN_PROMPT,
}


def get_prompt_for_task(task_type: str) -> str:
    """Get the default prompt for a task type.

    Args:
        task_type: Type of task ("describe_media" or "table_to_markdown")

    Returns:
        Prompt string for the task

    Raises:
        ValueError: If task_type is not recognized
    """
    prompt = _TASK_PROMPTS.get(task_type)
    if prompt is None:
        raise ValueError(
            f"Unknown task type: {task_type}. "
            f"Available types: {list(_TASK_PROMPTS.keys())}"
        )
    return prompt


def get_available_task_types() -> list[str]:
    """Get list of available task types.

    Returns:
        List of task type strings
    """
    return list(_TASK_PROMPTS.keys())
