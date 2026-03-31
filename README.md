# 🌏 ec-translate

A Claude skill for translating e-commerce UI copy into 6 languages with platform-native quality.

## What It Does

Feed it any e-commerce UI text — button labels, toast messages, campaign descriptions, or full promotional paragraphs — and it outputs localized versions in a clean Markdown table:

| EN | ZH-CN | ZH-HK/TW | KO | JA | FR |
|----|-------|-----------|----|----|-----|
| Add to Cart | 加入购物车 | 加入購物車 | 장바구니 담기 | カートに入れる | Ajouter au panier |
| Buy Now | 立即购买 | 立即購買 | 바로 구매 | 今すぐ購入 | Acheter |

## Supported Languages

- **English (EN)**
- **Simplified Chinese (ZH-CN)**
- **Traditional Chinese (ZH-HK/TW)** — Hong Kong / Taiwan standard
- **Korean (KO)**
- **Japanese (JA)**
- **French (FR)**

## Features

### Smart Input Detection

The skill automatically detects what you provide and adapts:

- **English only** → translates into the other 5 languages
- **Chinese only** → translates into the other 5 languages
- **Both EN + ZH** → cross-references both to resolve ambiguity, then translates the rest

### Copy-Length Awareness

Different UI contexts need different translation strategies:

| Type | Examples | Strategy |
|------|----------|----------|
| Short | Buttons, labels, status tags | Ultra-concise across all languages |
| Medium | Toasts, hints, subtitles | Preserve meaning, natural tone |
| Long | Campaign rules, onboarding text, policy summaries | Full sentences, proper honorifics, maintain paragraph structure |

### Japanese Optimization

Japanese translations adapt by copy length:

- **Short copy**: Prioritize katakana abbreviations and kanji compression. Target ≤ 8 characters for buttons. Skip particles and honorifics when context is clear.
- **Medium copy**: ≤ 15 characters, `ます` form.
- **Long copy**: Full `です・ます` honorific style. No readability sacrifice for brevity.

### French Optimization

French text is naturally 15–30% longer than English, so UI copy requires aggressive compression to avoid line-wrapping or truncation:

- **Short copy**: Stay within 1.2× the English character count. Use infinitives over full imperative sentences, abbreviate where possible (Qté, Livr. gratuite), and drop articles.
- **Medium copy**: Preserve meaning but cut unnecessary articles and prepositional phrases.
- **Long copy**: Use vouvoiement (vous) for politeness. No forced compression.

### Tone Neutrality

All translations avoid region-specific slang or overly casual internet language to stay professional and globally appropriate:

- ZH-CN: No Taobao-style terms like "亲", "宝子", "集美". Use "你" (informal you) instead of "您" (formal you) — targeting younger users
- ZH-HK/TW: No overly colloquial particles like "醬", "啦"
- JA: No casual sentence-final particles like 「ね」「よ」
- KO: User-facing copy always uses 존댓말 (formal speech)
- FR: Use vouvoiement (vous) in long copy for politeness; tutoiement (tu) acceptable in short, casual UI contexts

### Multi-Item Parsing

You can submit multiple items at once. The skill parses them intelligently:

- **Line breaks** → each line is a separate item
- **Slashes** → context-dependent: `Checkout / Wishlist` = two items; `Add to Cart / 加入购物车` = bilingual input for one item; `退款/退货` (Refund/Return) = one compound term
- **Commas** → never used as delimiters (they're often part of the copy itself)

## Usage

### For Claude Users

Drop the `ec-translate/` folder into your Claude skills directory. Claude will automatically activate the skill when you provide e-commerce UI text for translation — just type your copy and get results.

**File used:** `SKILL.md`

### For Other AI Tools (GPT, Gemini, Coze, etc.)

Copy the entire content of `ec-translate-prompt.md` and paste it into the **System Prompt** (or Custom Instructions / System Message) field of your AI tool. Then start a new conversation and type your e-commerce copy directly — the AI will follow the translation rules automatically.

**File used:** `ec-translate-prompt.md`

| Platform | Where to paste |
|----------|---------------|
| ChatGPT | Custom Instructions → System Message, or GPTs → Instructions |
| Gemini | Google AI Studio → System Instructions |
| Coze | Bot → Persona & Prompt |
| Dify / FastGPT | App → System Prompt |
| API calls | `system` field in the request body |

### Quick Examples

**Input:**
```
Checkout
```

**Output:**

| EN | ZH-CN | ZH-HK/TW | KO | JA | FR |
|----|-------|-----------|----|----|-----|
| Checkout | 结算 | 結帳 | 결제하기 | 購入手続きへ | Paiement |

**Input:**
```
新用户专享福利：注册即送50元优惠券礼包，包含满99减20券、满199减30券，有效期7天。
```

**Output:**

| EN | ZH-CN | ZH-HK/TW | KO | JA | FR |
|----|-------|-----------|----|----|-----|
| New user exclusive: Get a ¥50 coupon bundle upon registration, including ¥20 off on orders over ¥99 and ¥30 off on orders over ¥199. Valid for 7 days. | 新用户专享福利：注册即送50元优惠券礼包，包含满99减20券、满199减30券，有效期7天。 | 新用戶專享福利：註冊即送50元優惠券禮包，包含滿99減20券、滿199減30券，有效期7天。 | 신규 회원 전용 혜택: 가입 시 50위안 쿠폰 패키지를 드립니다. 99위안 이상 20위안 할인, 199위안 이상 30위안 할인 쿠폰이 포함되며, 유효기간은 7일입니다. | 新規ユーザー限定特典：ご登録で50元分のクーポンパックをプレゼントいたします。99元以上で20元OFF、199元以上で30元OFFのクーポンが含まれます。有効期限は7日間です。 | Offre nouveaux utilisateurs : recevez un pack de coupons de 50 ¥ à l'inscription, incluant 20 ¥ de réduction dès 99 ¥ et 30 ¥ dès 199 ¥. Valable 7 jours. |

## Batch Translation via Google Sheets

For teams managing large volumes of UI copy, `translate.py` automates the workflow: read source text from a Google Sheet → call AI API → write translations back.

### Prerequisites

```bash
pip install -r requirements.txt
```

1. Create a [Google Service Account](https://docs.gspread.org/en/latest/oauth2.html#for-bots-using-service-account) and download the credentials JSON
2. Share your Google Sheet with the service account email
3. Set environment variables:

```bash
export GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
export ANTHROPIC_API_KEY=sk-ant-...    # if using Claude
export OPENAI_API_KEY=sk-...           # if using OpenAI
```

### Sheet Format

Row 1 must be the header. Put source text in column A, and the script fills columns B–G:

| source | EN | ZH-CN | ZH-HK/TW | KO | JA | FR |
|--------|----|-------|-----------|----|----|-----|
| 加入购物车 | | | | | | |
| Buy Now | | | | | | |

Rows that already have all 6 translations filled will be skipped automatically.

### Run

```bash
# Using Claude (default)
python translate.py --sheet-id YOUR_SHEET_ID --provider claude

# Using OpenAI
python translate.py --sheet-id YOUR_SHEET_ID --provider openai

# Specify a worksheet tab
python translate.py --sheet-id YOUR_SHEET_ID --provider claude --sheet-name "Sheet2"

# Custom model
python translate.py --sheet-id YOUR_SHEET_ID --provider openai --model gpt-4o-mini

# Dry run (preview without calling API)
python translate.py --sheet-id YOUR_SHEET_ID --dry-run
```

The `--sheet-id` is the long string in your Google Sheet URL: `docs.google.com/spreadsheets/d/<THIS_PART>/edit`

## File Structure

```
ec-translate/
├── SKILL.md                 # Claude skill definition (Claude only)
├── ec-translate-prompt.md   # Universal system prompt (GPT, Gemini, Coze, etc.)
├── translate.py             # Batch translation script (Google Sheets + AI API)
├── requirements.txt         # Python dependencies
├── SETUP_GUIDE.md           # Step-by-step setup guide for Mac
└── README.md
```

## License

MIT
