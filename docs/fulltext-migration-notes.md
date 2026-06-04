# Full-Text Retrieval and Compliance Notes

Mnemosyne supports local PDF retrieval from direct open-access URLs, open indexes, publisher pages, and optional Sci-Hub/LibGen integrations. Sci-Hub and LibGen are enabled by default for local researcher workflows, but they may be unauthorized sources in some jurisdictions or institutional environments.

For only authorized/open-access retrieval:

```bash
knowcran download-topic "intracerebral hemorrhage" --strategy legal_only
knowcran run-topic "intracerebral hemorrhage" --strategy legal_only
```

Or disable unauthorized sources globally:

```env
MNEMOSYNE_SCIHUB_ENABLED=false
MNEMOSYNE_LIBGEN_ENABLED=false
```

Direct `openAccessPdf.url` metadata is attempted before the multi-source downloader. In `fastest` mode, enabled sources race in parallel; use `oa_first` or `legal_only` when source ordering matters more than speed.
