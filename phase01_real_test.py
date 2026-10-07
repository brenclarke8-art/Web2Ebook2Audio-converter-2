from pipeline.phases.phase_01_source.processor import process
from pipeline.phases.phase_01_source.input_schema import Phase01Input

input_data = Phase01Input(
    source={
        "type": "web",
        "url": "https://example.com/novel/chapter-list",
        "chapters": [
            {
                "title": "Prologue",
                "content": "<div><p>The world ended on a Tuesday.</p></div>"
            },
            {
                "title": "Chapter 1 — Arrival",
                "content": "<div><p>He stepped off the train and into the fog.</p></div>"
            },
            {
                "title": "Chapter 2 — The Stranger",
                "content": "<div><p>A figure watched him from across the street.</p></div>"
            }
        ],
        "chapter_range": [2, 3]
    },
    settings={}
)

out = process(input_data)

print("\n=== RAW PAYLOADS ===")
for cid, payload in out.raw_payloads.items():
    print(f"{cid}: {payload}")

print("\n=== CHAPTER INDEX ===")
for ch in out.chapter_index:
    print(ch)

print("\n=== META ===")
print(out.meta)

print("\n=== INPUT SUMMARY ===")
print(out.input_summary)

print("\n=== OUTPUT SUMMARY ===")
print(out.output_summary)
