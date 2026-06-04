from knowcran.paper_fetch.pdf_utils import safe_filename


def test_safe_filename_uses_arxiv_id_when_doi_missing():
    assert safe_filename("", arxiv_id="2301.12345") == "2301.12345.pdf"


def test_safe_filename_never_returns_empty_basename():
    assert safe_filename("", fallback="paper:1") == "paper_1.pdf"
