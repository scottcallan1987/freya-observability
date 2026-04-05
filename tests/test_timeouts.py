"""Tests for named timeout profile constants."""

from freya_observability import timeouts


class TestTimeoutConstants:
    def test_fast_is_five_seconds(self):
        assert timeouts.FAST == 5.0

    def test_normal_is_thirty_seconds(self):
        assert timeouts.NORMAL == 30.0

    def test_llm_is_one_twenty_seconds(self):
        assert timeouts.LLM == 120.0

    def test_crawl_is_three_hundred_seconds(self):
        assert timeouts.CRAWL == 300.0

    def test_all_timeouts_are_floats(self):
        for name in ("FAST", "NORMAL", "LLM", "CRAWL"):
            val = getattr(timeouts, name)
            assert isinstance(val, float), f"{name} must be a float, got {type(val)}"

    def test_ordering_is_monotonically_increasing(self):
        assert timeouts.FAST < timeouts.NORMAL < timeouts.LLM < timeouts.CRAWL
