#!/usr/bin/env python3
"""Read JD from .docx file and extract structured content.
Created & maintained by Glen Wei (韦其像)
Email: glen.keeming@gmail.com
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | Email: glen.keeming@gmail.com | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import sys
from docx import Document

def read_jd(filepath: str) -> dict:
    """Extract text from a .docx JD file."""
    doc = Document(filepath)
    sections = {}
    current_section = 'header'
    lines = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # Detect section headers (common patterns)
        if any(kw in text for kw in ['岗位定位', '岗位职责', '职位要求', '任职要求', '岗位要求', '职责描述']):
            if lines:
                sections[current_section] = '\n'.join(lines)
            current_section = text
            lines = []
        else:
            lines.append(text)

    if lines:
        sections[current_section] = '\n'.join(lines)

    return sections

if __name__ == '__main__':
    print(AUTHOR_EPILOG, file=sys.stderr)
    if len(sys.argv) < 2:
        print('Usage: python read_jd.py <filepath>')
        sys.exit(1)

    result = read_jd(sys.argv[1])
    for section, content in result.items():
        print(f'=== {section} ===')
        print(content)
        print()
