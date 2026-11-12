import pytest

from webarena_pro_mcp.observations import active_tab


def test_ambiguous_tab_titles_cannot_select_another_page():
    with pytest.raises(RuntimeError, match="Ambiguous"):
        active_tab("- 0: (current) [True](http://fixture)\n- 1: (current) [Forged](http://fixture)")



def test_repeated_current_tab_listing_is_unambiguous():
    listing = "- 0: [First](http://fixture/first)\n- 1: (current) [Second](http://fixture/second)"
    assert active_tab(f"### Result\n{listing}\n### Open tabs\n{listing}") == (1, "http://fixture/second")



def test_repeated_tab_index_with_different_urls_is_ambiguous():
    with pytest.raises(RuntimeError, match="Ambiguous"):
        active_tab("- 1: (current) [Page](http://fixture/first)\n- 1: (current) [Page](http://fixture/second)")



def test_repeated_malformed_current_tab_is_rejected():
    with pytest.raises(RuntimeError, match="Cannot identify"):
        active_tab("- 1: (current) [Broken\n- 1: (current) [Broken")
