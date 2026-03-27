from src.data.alternative.policy_radar.policy_crawler import PolicyCrawler, PolicySource
from src.data.alternative.policy_radar.official_feeds import OFFICIAL_FEED_ADAPTERS
from src.data.alternative.policy_radar.policy_nlp import PolicyNLPAnalyzer
from src.data.alternative.policy_radar.policy_signals import PolicySignalProvider


class _Response:
    def __init__(self, text: str, encoding: str = "utf-8"):
        self.text = text
        self.encoding = encoding


def test_policy_crawler_prefers_feed_and_enriches_details(monkeypatch):
    crawler = PolicyCrawler(
        sources={
            "fed": PolicySource(
                name="Fed",
                base_url="https://www.federalreserve.gov",
                list_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
                feed_url="https://www.federalreserve.gov/feeds/press_all.xml",
                language="en",
            )
        }
    )

    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Fed Keeps Policy Steady</title>
          <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260326a.htm</link>
          <pubDate>Thu, 26 Mar 2026 14:00:00 GMT</pubDate>
          <description>Official statement on monetary policy stance.</description>
        </item>
      </channel>
    </rss>
    """
    def fake_request(url, timeout=30, **kwargs):
        if url.endswith(".xml"):
            return _Response(feed_xml)
        raise AssertionError(f"Unexpected url: {url}")

    monkeypatch.setattr(crawler, "_safe_request", fake_request)
    monkeypatch.setattr(
        crawler,
        "fetch_policy_detail",
        lambda url, source_id: {
            "url": url,
            "title": "Fed Release",
            "text": "The Federal Reserve maintained the target range and highlighted persistent inflation moderation.",
            "text_length": 92,
        },
    )

    policies = crawler.crawl_source("fed", limit=3, days_back=30, fetch_details=True, detail_limit=1)
    assert len(policies) == 1
    assert policies[0]["ingest_mode"] == "feed"
    assert "maintained the target range" in policies[0]["text"]
    assert policies[0]["detail_excerpt"]
    assert policies[0]["text_length"] > 20
    assert policies[0]["feed_adapter"] == "generic_rss"


def test_policy_crawler_uses_named_feed_adapter():
    crawler = PolicyCrawler()
    source = crawler.sources["fed"]
    adapter = OFFICIAL_FEED_ADAPTERS[source.feed_adapter]
    assert source.feed_adapter == "fed_press"
    assert adapter is not None


def test_policy_signal_provider_keeps_detail_excerpt_in_records(monkeypatch):
    provider = PolicySignalProvider(config={"nlp_mode": "local"})

    monkeypatch.setattr(
        provider.crawler,
        "crawl_source",
        lambda *args, **kwargs: [
            {
                "title": "Grid investment policy update",
                "summary": "Policy summary line",
                "detail_excerpt": "Detailed policy excerpt about grid investment acceleration.",
                "text": "Detailed policy excerpt about grid investment acceleration.",
                "text_length": 64,
                "date": "2026-03-26",
                "source": "国家发改委",
                "source_id": "ndrc",
                "link": "https://example.com/policy",
                "detail_url": "https://example.com/policy",
                "detail_title": "Grid investment policy update",
                "ingest_mode": "feed",
            }
        ],
    )

    signal = provider.run_pipeline(sources=["ndrc"], limit=1, days_back=7, fetch_details=True)
    history = provider.get_history(limit=1)

    assert signal["record_count"] == 1
    assert history[0].raw_value["excerpt"].startswith("Detailed policy excerpt")
    assert history[0].raw_value["text_length"] == 64
    assert history[0].metadata["ingest_mode"] == "feed"
    assert history[0].metadata["detail_status"] == "summary_only"
    assert "source_health" in signal
    assert signal["source_health"]["ndrc"]["level"] in {"watch", "fragile"}


def test_policy_nlp_local_recognizes_english_policy_bias():
    analyzer = PolicyNLPAnalyzer(mode="local")
    result = analyzer.analyze(
        title="ECB supports grid investment and energy storage buildout",
        text=(
            "The central bank must support infrastructure investment, expand liquidity support "
            "and accelerate grid and energy storage capacity expansion without delay."
        ),
        source="ECB",
    )

    assert result["policy_shift"] > 0
    assert result["will_intensity"] > 0
    assert "电网" in result["industry_impact"] or "储能" in result["industry_impact"]


def test_policy_signal_provider_source_health_marks_full_text_as_healthier(monkeypatch):
    provider = PolicySignalProvider(config={"nlp_mode": "local"})
    monkeypatch.setattr(
        provider.crawler,
        "crawl_source",
        lambda *args, **kwargs: [
            {
                "title": "Fed grid policy",
                "summary": "Short summary",
                "detail_excerpt": "A long detailed policy text. " * 40,
                "text": "A long detailed policy text. " * 40,
                "text_length": 1100,
                "detail_status": "full_text",
                "detail_quality": "rich",
                "date": "2026-03-26",
                "source": "Fed",
                "source_id": "fed",
                "link": "https://example.com/fed",
                "detail_url": "https://example.com/fed",
                "detail_title": "Fed grid policy",
                "ingest_mode": "feed",
            }
        ],
    )

    signal = provider.run_pipeline(sources=["fed"], limit=1, days_back=7, fetch_details=True)
    health = signal["source_health"]["fed"]
    assert health["full_text_ratio"] == 1.0
    assert health["avg_text_length"] >= 1000
    assert health["level"] == "healthy"
