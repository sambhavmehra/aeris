"""
Verification test script for Word tools.
Tests video ID extraction, page scraping, Docx formatting, and integration.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools.word_tools import (
    extract_youtube_video_id,
    scrape_web_link,
    extract_transcript_to_word
)


def test_youtube_video_id_extraction():
    print("Testing YouTube Video ID extraction...")
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=44",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
        "dQw4w9WgXcQ"
    ]
    for url in urls:
        video_id = extract_youtube_video_id(url)
        print(f"  URL: {url:<60} => Video ID: {video_id}")
        assert video_id == "dQw4w9WgXcQ", f"Failed for {url}: got {video_id}"
    print("OK: YouTube Video ID extraction tests passed.")


def test_webpage_scraping():
    print("\nTesting general webpage scraping...")
    # Use a safe public HTTP endpoint or simple site
    url = "https://example.com"
    try:
        content = scrape_web_link(url)
        print(f"  Scraped successfully (length: {len(content)} chars)")
        print(f"  Content snippet: {content[:100]}...")
        assert "Example Domain" in content, "Example Domain text not found in scraped content"
        print("OK: Webpage scraping test passed.")
    except Exception as e:
        print(f"FAIL: Webpage scraping failed: {e}")


async def test_notes_generation_and_docx():
    print("\nTesting notes generation and styled Docx file saving...")
    test_text = (
        "# Introduction to AI Agents\n\n"
        "AI agents are autonomous software entities that can perceive their environment, "
        "make decisions, and take actions to achieve specific goals.\n\n"
        "## Core Components of Agents\n\n"
        "- **Planning**: Breaking tasks into sub-steps and thinking dynamically.\n"
        "- **Memory**: Retaining context over short-term and long-term interactions.\n"
        "- **Tools**: Capabilities like browser automation, code execution, and searches.\n\n"
        "> AI agents represent the next major shift in software development.\n\n"
        "### Action Items\n\n"
        "1. Install the `python-docx` library.\n"
        "2. Register the tool in `tool_registry.py`.\n"
        "3. Test the script.\n"
    )
    
    # We will generate a document directly using the 'text' parameter
    output_file = "scratch/test_ai_notes.docx"
    output_path = backend_dir / output_file
    if output_path.exists():
        output_path.unlink()

    print(f"  Generating Word file using direct text at: {output_path}")
    result = await extract_transcript_to_word(
        text=test_text,
        output_path=str(output_path),
        notes_style="detailed"
    )
    print(f"  Result message: {result}")
    
    # Verify file was created
    assert output_path.exists(), "Word document was not created"
    assert output_path.stat().st_size > 0, "Word document is empty"
    print(f"OK: Notes Word document created successfully (size: {output_path.stat().st_size} bytes)")


async def main():
    try:
        test_youtube_video_id_extraction()
        test_webpage_scraping()
        await test_notes_generation_and_docx()
        print("\nAll tests completed successfully!")
    except AssertionError as ae:
        print(f"\nAssertion Error: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest Execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
