#!/usr/bin/env python3
"""
ec-translate: Batch translate e-commerce UI copy via Google Sheets.

Reads source text from a Google Sheet, translates into 5 languages
using Claude or OpenAI API, and writes results back to the same sheet.

Usage:
    python translate.py --sheet-id <GOOGLE_SHEET_ID> --provider claude
    python translate.py --sheet-id <GOOGLE_SHEET_ID> --provider openai
    python translate.py --sheet-id <GOOGLE_SHEET_ID> --provider claude --sheet-name "Sheet2"
    python translate.py --sheet-id <GOOGLE_SHEET_ID> --provider openai --model gpt-4o

Setup:
    1. pip install gspread anthropic openai
    2. Set up Google Service Account and download credentials JSON
       → https://docs.gspread.org/en/latest/oauth2.html#for-bots-using-service-account
    3. Share your Google Sheet with the service account email
    4. Set environment variables:
       - GOOGLE_CREDENTIALS_PATH: path to service account JSON file
       - ANTHROPIC_API_KEY: (if using --provider claude)
       - OPENAI_API_KEY: (if using --provider openai)

Sheet format:
    The script expects the following column layout (row 1 = header):

    | source | EN | ZH-CN | ZH-HK/TW | KO | JA |
    |--------|----|-------|-----------|----|----|
    | 加入购物车 |  |       |           |    |    |
    | Buy Now   |  |       |           |    |    |

    - Column A ("source"): the original text to translate
    - Columns B-F: translation outputs (filled by the script)
    - Rows with all 5 translation columns already filled will be skipped
    - Empty source rows are ignored
"""

import argparse
import json
import os
import re
import sys
import time

import gspread

# ---------------------------------------------------------------------------
# System prompt (embedded from ec-translate-prompt.md)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = r"""你是一位电商平台用户界面（UI）多语言翻译专家。用户会向你提供电商场景下的 UI 文案，你需要将其翻译为 5 种语言。

翻译规范：
- 电商语境优先：使用电商 App/Web 常用术语（"购物车"而非"买菜篮"，"立即购买"而非"现在支付"）
- 语气中立：避免各语言中带有特定地区色彩的网络流行语（简中避免"亲""宝子"，对用户称谓统一用"你"而非"您"；繁中避免"醬""啦"；日文避免随意终助词；韩文统一使用존댓말）
- 日文特化：短文案（按钮）≤8字符，优先片假名缩写和汉字词压缩，省略助词敬语；中等文案≤15字符用「ます」体；长段文案必须用完整「です・ます」敬语体
- 繁体标准：使用港台通用电商术语（存储器→記憶體，支持→支援，信息→訊息）
- UI 文案简洁性：所有语言在不损失语义的前提下尽量精简

输出格式：严格以 JSON 数组返回，每个元素包含 5 个 key：EN, ZH-CN, ZH-HK/TW, KO, JA。
不要输出任何多余文字、解释或 Markdown，只输出纯 JSON。

示例：
输入：加入购物车
输出：[{"EN": "Add to Cart", "ZH-CN": "加入购物车", "ZH-HK/TW": "加入購物車", "KO": "장바구니 담기", "JA": "カートに入れる"}]

输入（多条，用 ||| 分隔）：加入购物车 ||| Buy Now
输出：[{"EN": "Add to Cart", "ZH-CN": "加入购物车", "ZH-HK/TW": "加入購物車", "KO": "장바구니 담기", "JA": "カートに入れる"}, {"EN": "Buy Now", "ZH-CN": "立即购买", "ZH-HK/TW": "立即購買", "KO": "바로 구매", "JA": "今すぐ購入"}]
"""

LANG_KEYS = ["EN", "ZH-CN", "ZH-HK/TW", "KO", "JA"]
BATCH_SIZE = 10  # rows per API call
RATE_LIMIT_SLEEP = 1  # seconds between API calls


# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

def connect_sheet(sheet_id: str, sheet_name: str | None = None) -> gspread.Worksheet:
    """Connect to a Google Sheet and return the worksheet."""
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        print("Error: Set GOOGLE_CREDENTIALS_PATH to your service account JSON file path.")
        sys.exit(1)

    gc = gspread.service_account(filename=creds_path)
    spreadsheet = gc.open_by_key(sheet_id)

    if sheet_name:
        worksheet = spreadsheet.worksheet(sheet_name)
    else:
        worksheet = spreadsheet.sheet1

    return worksheet


def read_source_rows(ws: gspread.Worksheet) -> list[dict]:
    """
    Read the sheet and return rows that need translation.
    Returns list of {"row_index": int, "source": str}
    """
    all_values = ws.get_all_values()
    if not all_values:
        return []

    # Validate header
    header = [h.strip() for h in all_values[0]]
    expected = ["source", "EN", "ZH-CN", "ZH-HK/TW", "KO", "JA"]
    header_lower = [h.lower() for h in header]
    expected_lower = [h.lower() for h in expected]

    if header_lower[:6] != expected_lower:
        print(f"Error: Sheet header mismatch.")
        print(f"  Expected: {expected}")
        print(f"  Got:      {header[:6]}")
        print("Please make sure row 1 has: source | EN | ZH-CN | ZH-HK/TW | KO | JA")
        sys.exit(1)

    rows_to_translate = []
    for i, row in enumerate(all_values[1:], start=2):  # row 2 onwards (1-indexed)
        source = row[0].strip() if row else ""
        if not source:
            continue

        # Check if all 5 lang columns are already filled
        lang_values = [row[j].strip() if j < len(row) else "" for j in range(1, 6)]
        if all(lang_values):
            continue  # skip already translated rows

        rows_to_translate.append({"row_index": i, "source": source})

    return rows_to_translate


def write_translations(ws: gspread.Worksheet, row_index: int, translations: dict):
    """Write translation results to columns B-F of a given row."""
    cells = []
    for col_offset, key in enumerate(LANG_KEYS):
        value = translations.get(key, "")
        cells.append(gspread.Cell(row=row_index, col=col_offset + 2, value=value))

    if cells:
        ws.update_cells(cells, value_input_option="RAW")


# ---------------------------------------------------------------------------
# AI provider abstraction
# ---------------------------------------------------------------------------

def call_claude(texts: list[str], model: str) -> list[dict]:
    """Call Claude API to translate a batch of texts."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    user_content = " ||| ".join(texts)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    return parse_json_response(raw, len(texts))


def call_openai(texts: list[str], model: str) -> list[dict]:
    """Call OpenAI API to translate a batch of texts."""
    import openai

    client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    user_content = " ||| ".join(texts)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()
    return parse_json_response(raw, len(texts))


def parse_json_response(raw: str, expected_count: int) -> list[dict]:
    """Parse the AI response JSON, with fallback for markdown fences."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON response: {e}")
        print(f"  Raw response: {raw[:500]}")
        return [{}] * expected_count

    if isinstance(result, dict):
        result = [result]

    # Pad if response is shorter than expected
    while len(result) < expected_count:
        result.append({})

    return result[:expected_count]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ec-translate: Batch translate e-commerce UI copy via Google Sheets."
    )
    parser.add_argument(
        "--sheet-id", required=True,
        help="Google Sheet ID (from the URL: docs.google.com/spreadsheets/d/<THIS_PART>/edit)"
    )
    parser.add_argument(
        "--sheet-name", default=None,
        help="Worksheet/tab name (default: first sheet)"
    )
    parser.add_argument(
        "--provider", choices=["claude", "openai"], default="claude",
        help="AI provider to use (default: claude)"
    )
    parser.add_argument(
        "--model", default=None,
        help="Model name override (default: claude-sonnet-4-20250514 for Claude, gpt-4o for OpenAI)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Number of rows per API call (default: {BATCH_SIZE})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read sheet and show what would be translated, without calling API"
    )

    args = parser.parse_args()

    # Default models
    if args.model is None:
        args.model = "claude-sonnet-4-20250514" if args.provider == "claude" else "gpt-4o"

    translate_fn = call_claude if args.provider == "claude" else call_openai

    # Connect
    print(f"Connecting to Google Sheet: {args.sheet_id}")
    ws = connect_sheet(args.sheet_id, args.sheet_name)
    print(f"Worksheet: {ws.title}")

    # Read
    rows = read_source_rows(ws)
    if not rows:
        print("No rows to translate. All rows either have translations or are empty.")
        return

    print(f"Found {len(rows)} row(s) to translate.")

    if args.dry_run:
        print("\n[Dry Run] Rows to translate:")
        for r in rows:
            print(f"  Row {r['row_index']}: {r['source'][:80]}")
        return

    # Translate in batches
    total_batches = (len(rows) + args.batch_size - 1) // args.batch_size
    print(f"Translating with {args.provider} ({args.model}), {total_batches} batch(es)...\n")

    for batch_idx in range(0, len(rows), args.batch_size):
        batch = rows[batch_idx : batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1
        texts = [r["source"] for r in batch]

        print(f"[Batch {batch_num}/{total_batches}] Translating {len(batch)} row(s)...")

        try:
            results = translate_fn(texts, args.model)
        except Exception as e:
            print(f"  Error calling {args.provider} API: {e}")
            print("  Skipping this batch.")
            continue

        # Write results back
        for row_info, translation in zip(batch, results):
            if not translation:
                print(f"  Row {row_info['row_index']}: empty result, skipped")
                continue

            write_translations(ws, row_info["row_index"], translation)
            print(f"  Row {row_info['row_index']}: ✅ {row_info['source'][:40]}")

        # Rate limiting
        if batch_idx + args.batch_size < len(rows):
            time.sleep(RATE_LIMIT_SLEEP)

    print("\nDone! All translations written back to the sheet.")


if __name__ == "__main__":
    main()
