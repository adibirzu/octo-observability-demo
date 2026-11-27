from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
START = '/* BEGIN SHARED DESIGN TOKENS */'
END = '/* END SHARED DESIGN TOKENS */'


def test_shared_tokens_are_identical_in_packaged_stylesheets():
    source = (ROOT / 'shared/design/tokens.css').read_text()
    assert all(token in source for token in ('--color-surface:', '--font-body:', '--space-md:'))
    for app, css in [('shop', 'tokens.css'), ('crm', 'style.css')]:
        content = (ROOT / app / 'server/static/css' / css).read_text()
        assert content.split(START, 1)[1].split(END, 1)[0].strip() == source.strip()


def test_stylesheets_resolve_in_standalone_app_copies(tmp_path):
    for app in ('shop', 'crm'):
        server = ROOT / app / 'server'
        copy = tmp_path / app / 'server'
        shutil.copytree(server / 'static', copy / 'static')
        template = (server / 'templates/base.html').read_text()
        links = re.findall(r'href=["\'](/static/css/[^"\']+\.css)["\']', template)
        assert links
        for link in links:
            assert (copy / link.lstrip('/')).is_file()
