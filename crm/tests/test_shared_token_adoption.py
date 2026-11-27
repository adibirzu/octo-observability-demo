import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / 'server/static/css/style.css').read_text()


def rule(selector):
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', CSS):
        if selector in [part.strip() for part in match.group(1).split(',')]:
            return match.group(2)
    raise AssertionError(f'missing rule {selector}')


def test_shared_tokens_applied_to_components():
    for name in ('color-panel', 'color-line', 'color-accent', 'color-accent-strong',
                 'space-md', 'space-xs', 'radius-lg', 'radius-md'):
        assert re.search(rf'--{name}\s*:', CSS)
    card = rule('.card')
    button = rule('.btn')
    primary = rule('.btn-primary')
    for prefix in ('color', 'radius'):
        assert f'var(--{prefix}-' in card
    for prefix in ('space', 'radius'):
        assert f'var(--{prefix}-' in button
    assert 'var(--color-' in primary
    assert 'var(--space-' in rule('.content-body')


def test_focus_and_narrow_layout_remain_available():
    assert re.search(r':focus-visible\s*\{[^}]*outline:\s*2px solid', CSS)
    assert re.search(r'@media\s*\(max-width:\s*640px\).*?\.dashboard-grid\s*\{[^}]*grid-template-columns:\s*1fr', CSS, re.S)
    for state in ('.btn-success', '.btn-warning', '.btn-danger'):
        assert 'background:' in rule(state) and 'color:' in rule(state)


def test_login_rendered_with_and_without_sso():
    env = Environment(loader=FileSystemLoader(ROOT / 'server/templates'), autoescape=True)
    template = env.get_template('login.html')
    for configured in (True, False):
        html = template.render(idcs_configured=configured, request=None, app_name='CRM', brand_name='Demo', app_version='1', apm_console_url='', opsi_console_url='', db_management_console_url='', log_analytics_console_url='')
        assert 'login-card' in html and 'btn btn-primary' in html
        assert ('btn-sso' in html) is configured
        assert 'login-error' in html and 'Login failed:' in html
