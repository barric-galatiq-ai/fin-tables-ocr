# fin-tables-ocr

Extract transaction data from bank statement PDFs.

Despite the name, this tool doesn't perform OCR. It parses text-based PDFs using pdfplumber to extract embedded text and table structures. Works with digital/native PDFs, not scanned images.

## Installation

```bash
pip install -e .
```

## Usage

```bash
fin-tables-ocr extract statement.pdf --keywords keywords.json --output ./output
```

### Commands

- `extract` - Parse a PDF and output transactions to CSV and JSON
- `info` - Show detected bank info without extracting

## Supported Banks

- Truist

## Keywords File

The `--keywords` option takes a JSON file for tagging transactions with lender information (transfers and payments).
