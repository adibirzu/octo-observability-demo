import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_trend_card_renders_only_supplied_samples():
    template = (ROOT / 'server/templates/observability.html').read_text()
    assert 'id="signal-trend"' in template
    assert 'renderSignalTrend((payload.charts || {}).signal_trend)' in template
    script = template.split('function renderSignalTrend(', 1)[1].split('\nfunction ', 1)[0]
    fixtures = json.loads((ROOT / 'tests/fixtures/observability_trend.json').read_text())
    program = '''
const element = {innerHTML: ''};
const document = {getElementById: () => element};
function escapeHtml(value) { return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function renderSignalTrend(''' + script + '''
const fixtures = JSON.parse(process.argv[1]);
for (const [name, data] of Object.entries(fixtures)) { renderSignalTrend(data); console.log(JSON.stringify([name, element.innerHTML])); }
renderSignalTrend({samples: [{time: '<script>', value: 1}, {time: 'later', value: null}]}); console.log(JSON.stringify(['escaped', element.innerHTML]));
renderSignalTrend({samples: Array(25).fill({time: 'x', value: 1})}); console.log(JSON.stringify(['oversized', element.innerHTML]));
'''
    result = subprocess.run(['node', '-e', program, json.dumps(fixtures)], check=True, capture_output=True, text=True)
    cards = dict(json.loads(line) for line in result.stdout.splitlines())
    assert 'Missing' in cards['missing'] and '<svg' not in cards['missing']
    assert 'Partial' in cards['partial'] and '09:05' in cards['partial'] and 'missing' in cards['partial'].lower()
    assert 'Observed' in cards['observed'] and '<svg' in cards['observed']
    assert '09:00' in cards['observed'] and '09:10' in cards['observed']
    assert 'Missing' in cards['oversized'] and '<svg' not in cards['oversized']
    assert '&lt;script&gt;' in cards['escaped'] and '<script>' not in cards['escaped']
    assert '<line' not in cards['partial']
