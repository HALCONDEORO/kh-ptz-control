# Project website

`docs/index.html` is the English project website. It is a static page with no
JavaScript, third-party fonts, analytics, cookies or build dependencies. CSS and
the reviewed demonstration screenshot are in `docs/site/`.

## Preview locally

From the repository root:

```bash
python3 -m http.server 8000 --directory docs
```

Open `http://localhost:8000/`. This server is for local preview, not production.
Check desktop and mobile widths, keyboard navigation, installation commands,
links and the current product limitations before publishing.

```bash
python3 -m pytest tests/test_project_pages.py tests/test_markdown_links.py
```

The screenshot is a real `MainWindow` capture in local USER-mode simulation,
refreshed on 25 November 2026 with the light blue-gray auditorium background, the camera power toggle, Comments → Home and the quiet offline Help entry below Admin Mode. The README banner and docs/screenshots 01-03 were regenerated from the same simulation.
It uses the repository background (`ui/khptz_background.jpg`) and is 1920 × 1080.
The view contains numbered seats, no assigned names or device addresses.
Temporary app/config/data directories and simulated connection indicators were
used; no real equipment was connected. The main STOP ALL button is hidden
in USER and visible after ADMIN elevation; Help offers STOP BOTH CAMERAS to USER. This is not a physical camera test.
Re-review replacements before committing them.

## Live GitHub Pages

The site is active at <https://halcondeoro.github.io/kh-ptz-control/>.
Pages was enabled on 11 November 2026 with the owner's approval, using
**Deploy from a branch**, branch `main`, folder **/docs**, with HTTPS enforced.
`docs/.nojekyll` keeps it a plain static site. Reviewed merges to `main`
automatically update this public site; no hardware deployment is involved.

For each update, require exact-head review and complete CI before merge, then
check the Pages build commit, public HTTP result and actual desktop/mobile
pixels. A successful build alone does not prove the right content is live.
Do not change repository visibility, branch protection, permissions or the
publishing source as part of a documentation edit.

The public page links technical guides to their repository versions so it does
not need to duplicate the installation documentation. Update the page's review
date and source claims when installation targets or ATEM gates change.

## Optional UI walkthrough

`docs/site/ui-walkthrough.mp4` contains four captured `MainWindow` states from
commit `306c17e6decb3940343e21f98eac07ce79ee4461`, captured on 10 November 2026:
Platform selected, Comments selected, simulated disconnect, simulated recovery.
It has no audio and is labelled as simulation on every frame. Temporary app,
configuration and data directories were used, with loopback simulation targets;
camera workers and background timers were stopped before capturing the states.
The UI states were injected for illustration, not observed physical outcomes.
No camera movement or preset writes were requested.

The website uses native manual video controls, `preload="none"`, no autoplay,
no looping and a local poster. The four-scene text transcript stays visible.
The original UI pixels are preserved below a separate caption strip, scaled
proportionally. Review every frame before replacing the video; omit names,
device addresses, login/configuration details and private site data. The video
does not validate CALL, SET, STOP delivery or physical recovery.
