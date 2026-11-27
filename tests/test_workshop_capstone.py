from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_capstone_is_linked_and_self_contained():
    lab = (ROOT / 'site/workshop/lab-19-six-pillar-capstone.md').read_text()
    index = (ROOT / 'site/workshop/index.md').read_text()
    nav = (ROOT / 'mkdocs.yml').read_text()
    assert 'lab-19-six-pillar-capstone.md' in index
    assert 'workshop/lab-19-six-pillar-capstone.md' in nav
    for phrase in ('offline', 'order-1042', '0123456789abcdef0123456789abcdef',
                   'oracleApmTraceId', 'payment.status', 'security signal',
                   'GenAI', 'infrastructure', 'metric', 'synthetic', 'unverified'):
        assert phrase.lower() in lab.lower(), phrase
    assert 'lab-18-payment-failure-rca-apm.md' in lab
