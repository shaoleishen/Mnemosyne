# PDF Download Sources

This document describes the PDF download sources available in Mnemosyne.

## Source List

| Source | Priority | Type | Description |
| --- | --- | --- | --- |
| arXiv | 10 | Open Access | Direct PDF download from arxiv.org |
| Unpaywall | 20 | Open Access | Open access PDF lookup via DOI |
| OpenAlex | 25 | Open Access | Open access PDF lookup |
| Semantic Scholar | 30 | Open Access | PDF from openAccessPdf metadata |
| EuropePMC | 35 | Open Access | Full text from Europe PMC |
| PMC | 40 | Open Access | PubMed Central free PDF |
| CORE | 45 | Open Access | Open access research papers |
| DOAJ | 50 | Open Access | Directory of Open Access Journals |
| Crossref | 55 | Open Access | Publisher link lookup via DOI |
| Publishers | 60 | Mixed | Direct publisher PDF links |
| LibGen | 80 | Grey | Library Genesis (see compliance warning) |
| Sci-Hub | 90 | Grey | Sci-Hub (see compliance warning) |

## Compliance Warning

**Default mode enables Sci-Hub and LibGen.** This provides high PDF access success but creates legal and institutional compliance risk.

### Recommendations

- **Individual researchers**: Use at your own discretion. Check your jurisdiction's copyright laws.
- **Institutional users**: Set `MNEMOSYNE_PDF_STRATEGY=legal_only` to disable grey sources.
- **Published work**: Always verify PDF availability through legal channels first.

### Legal-Only Mode

To use only legal/open access sources:

```bash
export MNEMOSYNE_PDF_STRATEGY=legal_only
knowcran download-topic "topic" --strategy legal_only
```

Or in `.env`:

```
MNEMOSYNE_PDF_STRATEGY=legal_only
MNEMOSYNE_SCIHUB_ENABLED=false
MNEMOSYNE_LIBGEN_ENABLED=false
```

## Source Behavior

### DOI Resolution Order

1. Try DOI-based sources first (Unpaywall, OpenAlex, Semantic Scholar, Crossref, Publishers)
2. Fall back to arXiv ID if available
3. Fall back to title-based search

### Caching

- Downloaded PDFs are cached in `data/pdfs/`
- Filename is based on DOI or title slug
- SHA-256 hash is computed and stored in database
- Existing valid PDFs are skipped unless `--force` is used

### Racing

In `fastest` mode, all enabled sources are queried in parallel. The first successful download wins. Failed sources are logged but don't block the download.

## Troubleshooting

### No PDF found

- Check if the paper has a DOI: `knowcran show-paper <paper_id>`
- Try different strategies: `--strategy oa_first` or `--strategy legal_only`
- Check source availability: some sources may be temporarily unavailable

### Invalid PDF

- PDFs are validated by magic bytes and EOF marker
- Encrypted PDFs are detected and flagged
- Scanned PDFs (no text) are flagged as `needs_ocr`

### Performance

- Batch downloads use `MNEMOSYNE_PDF_BATCH_WORKERS` (default: 5)
- Each source has a 30-second timeout
- Overall download timeout is 60 seconds per paper
