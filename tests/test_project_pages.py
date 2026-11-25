"""The public project page is static, navigable, and backed by repository files."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.assets, self.images = set(), [], [], []
        self.lang = None
        self.scripts = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.lang = attrs.get('lang')
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.assets.append(attrs['href'])
        if tag == 'img':
            self.assets.append(attrs['src'])
            self.images.append(attrs)
        if tag == 'script':
            self.scripts += 1


def test_public_page_contract():
    source = ROOT / 'docs/index.html'
    assert source.is_file()
    text = source.read_text()
    page = Page()
    page.feed(text)
    assert page.lang == 'en'
    assert {'install', 'operate', 'atem', 'architecture', 'help'} <= page.ids
    assert 'physical validation' in text.lower()
    assert 'GPL' in text
    assert page.scripts == 0
    assert all(image.get('alt') and image.get('width') and image.get('height') for image in page.images)
    for target in page.links:
        if target.startswith('#'):
            assert target[1:] in page.ids, target
        elif '/blob/main/' in target:
            assert (ROOT / target.split('/blob/main/', 1)[1]).is_file(), target
    for asset in page.assets:
        assert not asset.startswith(('https:', 'http:'))
        assert (source.parent / asset).is_file(), asset
    assert not re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text), 'No device addresses on the public page'
    assert 'copyright' not in text.lower()
    image = page.images[0]
    data = (source.parent / image['src']).read_bytes()
    marker = data.index(b'\x9d\x01\x2a') + 3  # WebP VP8 keyframe dimensions
    import struct
    width, height = struct.unpack('<HH', data[marker:marker + 4])
    assert (int(image['width']), int(image['height'])) == (width & 0x3fff, height & 0x3fff)
    readme_text = (ROOT / 'README.md').read_text()
    assert 'Resumen en español' not in readme_text
    for code in ('es', 'pt', 'fr', 'de', 'it'):
        assert f'docs/translations/README.{code}.md' in readme_text
        assert (ROOT / 'docs' / 'translations' / f'README.{code}.md').is_file()


def test_task_routes_checkpoints_and_limits():
    text = (ROOT / 'docs/index.html').read_text()
    page = Page()
    page.feed(text)
    assert {'start', 'checkpoints', 'faq'} <= page.ids
    assert 'Choose your next step' in text
    assert 'What this project does not do' in text
    assert text.count('<details>') >= 3
    assert 'Expected result' in text
    readme = (ROOT / 'README.md').read_text()
    assert '## Start here' in readme
    assert '## What this project does not do' in readme


def test_public_entry_points_use_neutral_venue_language():
    for relative in ('docs/index.html', 'README.md', 'docs/PAGES.md'):
        text = (ROOT / relative).read_text().lower()
        assert 'for_kingdom_halls' not in text, relative
        assert not re.search(r'\b(?:halls?|congregation|congregación)\b', text), relative


def test_demo_is_manual_local_and_transcribed():
    text = (ROOT / 'docs/index.html').read_text()
    page = Page()
    page.feed(text)
    assert 'demo-transcript' in page.ids
    assert 'UI state walkthrough' in text
    videos = re.findall(r'<video\b([^>]*)>', text)
    assert len(videos) == 1
    attrs = videos[0]
    assert 'controls' in attrs and 'preload="none"' in attrs
    assert 'autoplay' not in attrs and 'loop' not in attrs
    assert 'width="1280"' in attrs and 'height="790"' in attrs
    assert 'aria-describedby="demo-transcript"' in attrs
    assert 'poster="site/demo-poster.webp"' in attrs
    assert 'src="site/ui-walkthrough.mp4"' in text
    assert 'No physical camera test' in text
    for label in ('Choose Platform', 'Choose Comments', 'Hold the joystick', 'Release the joystick'):
        assert label in text
    video = ROOT / 'docs/site/ui-walkthrough.mp4'
    assert video.is_file()
    assert b'ftyp' == video.read_bytes()[4:8]
    assert video.stat().st_size < 200_000
    assert (ROOT / 'docs/site/demo-poster.webp').is_file()


def test_operator_entry_points_do_not_promise_unwired_safety_buttons():
    for relative in ('docs/index.html', 'README.md'):
        text = (ROOT / relative).read_text()
        assert 'not a verified' in text, relative
        assert 'STOP ALL' in text, relative
        assert 'Learn STOP, STOP ALL' not in text, relative
        assert 'Learn [STOP, STOP ALL' not in text, relative


def test_setup_scope_and_demo_age_are_visible():
    """Setup has no layout editor; the walkthrough is a dated simulator recording."""
    readme = (ROOT / 'README.md').read_text()
    page = (ROOT / 'docs/index.html').read_text()
    assert 'wizard collects camera IPs, seat layout' not in readme
    assert 'wizard collects camera configuration, the layout' not in page
    assert 'room details, camera addresses and login settings' in readme
    assert 'room details, camera addresses and login settings' in page
    assert 'recorded 25 November 2026' in page
    assert 'built-in simulator' in page
    assert 'It is not the installed system' in page


def test_walkthrough_disclaimer_has_small_text_contrast():
    css = (ROOT / 'docs/site/styles.css').read_text()
    # The local override uses the established body ink, not the lighter muted ink.
    assert '.walkthrough>p.muted{color:var(--body)}' in css
    foreground = re.search(r'--body:#([0-9a-f]{6})', css)[1]
    background = re.search(r'\.use-section\{background:#([0-9a-f]{6})', css)[1]

    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

    low, high = sorted((luminance(foreground), luminance(background)))
    assert (high + .05) / (low + .05) >= 4.5
def test_install_requires_reviewed_revision_before_privileged_steps():
    page = (ROOT / 'docs/index.html').read_text()
    install = page.split('id="install"', 1)[1].split('id="operate"', 1)[0]
    commands = '\n'.join(re.findall(r'<pre><code>(.*?)</code></pre>', install, re.S))
    before_install = commands.split('sudo bash install_khptz_rpi.sh', 1)[0]
    assert 'git checkout --detach "$APPROVED_REVISION"' in before_install
    assert 'git rev-parse HEAD' in before_install
    assert 'read -r -p' in before_install
    assert 'Do not continue if checkout fails' in install


def test_install_commands_have_explicit_stages_and_stop_rules():
    text = (ROOT / 'docs/index.html').read_text()
    install = text.split('id="install"', 1)[1].split('id="operate"', 1)[0]
    stages = ['1. Choose the reviewed build', '2. Check readiness', '3. Install only after PASS', '4. Complete setup']
    assert all(f'<h3>{stage}</h3>' in install for stage in stages)
    assert [install.index(stage) for stage in stages] == sorted(install.index(stage) for stage in stages)
    assert 'Do not continue if checkout fails' in install
    assert 'not the service account' in install
    assert 'If it fails, stop' in install

def test_help_precedes_optional_contributor_content():
    text = (ROOT / 'docs/index.html').read_text()
    assert text.index('id="operate"') < text.index('id="help"') < text.index('id="atem"') < text.index('id="architecture"')
    atem = text.split('id="atem"', 1)[1].split('</section>', 1)[0]
    architecture = text.split('id="architecture"', 1)[1].split('</section>', 1)[0]
    assert '<details><summary>Optional ATEM integration and licence checks</summary>' in atem
    assert '<details><summary>For contributors: project architecture</summary>' in architecture
    assert 'GPL' in atem and 'Dependency decision and release gates' in atem

def test_first_screen_explains_product_audience_and_validation_state():
    page = (ROOT / 'docs/index.html').read_text()
    hero = page.split('<section class="hero wrap">', 1)[1].split('</section>', 1)[0]
    assert 'Touchscreen camera control.<br><em>For Raspberry Pi.</em>' in hero
    assert 'For room operators:' in hero
    assert 'VISCA-over-IP cameras' in hero
    assert hero.index('Target hardware validation is still pending') < hero.index('href="#install"')
    assert 'summary-band' not in page


def test_public_page_explains_user_and_admin_stop_routes():
    text = (ROOT / 'docs/index.html').read_text()
    assert 'The main STOP ALL button is ADMIN-only' in text
    assert 'STOP BOTH CAMERAS without confirmation' in text
    assert 'Opening Help sends no commands' in text
    assert 'Releasing the joystick requests a stop' in text
    assert 'Rehearse the red STOP ALL button in ADMIN mode' in text
    assert 'physical fallback available without a password' in text
    assert 'USER-mode simulation' in text


def test_readme_and_publication_notes_match_live_project():
    readme = (ROOT / 'README.md').read_text()
    pages = (ROOT / 'docs/PAGES.md').read_text()
    assert 'https://halcondeoro.github.io/kh-ptz-control/' in readme
    assert 'A live URL will be added' not in readme
    for stage in ('1. Choose the reviewed build', '2. Check readiness', '3. Install only after PASS', '4. Complete setup'):
        assert stage in readme
    assert 'git checkout --detach "$APPROVED_REVISION"' in readme
    assert '## Live GitHub Pages' in pages
    assert 'branch `main`, folder **/docs**' in pages
    assert 'USER has STOP BOTH CAMERAS inside offline Help' in (ROOT / 'docs/MVP_VALIDATION_REPORT.md').read_text()


def test_support_report_is_actionable_and_private():
    text = (ROOT / 'docs/index.html').read_text()
    report = text.split('id="report"', 1)[1].split('</aside>', 1)[0]
    for required in ('khptz version', 'expected result and actual result', 'simulation or real equipment', 'Review and redact logs', 'physical fallback first'):
        assert required in report
    assert 'https://github.com/HALCONDEORO/kh-ptz-control/issues' in report
