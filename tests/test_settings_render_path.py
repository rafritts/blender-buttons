"""Pure-Python guard for server/_settings.py render-path resolution (no Blender).

Run: python3 tests/test_settings_render_path.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _settings as s

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# defaults present even if settings.json is absent/garbage
d = s.load_settings()
check(d.get("render_dir"), "render_dir missing from settings")

RDIR = s.render_dir()
check(os.path.isabs(RDIR), f"render_dir not absolute/expanded: {RDIR}")
check("~" not in RDIR, f"render_dir still has ~: {RDIR}")

# 1. plain name -> configured dir, extension-less, 8-char base36 tag
p = s.resolve_render_path("donut_hero.png")
check(os.path.dirname(p) == RDIR.rstrip("/"), f"not in render_dir: {p}")
m = re.fullmatch(r"donut_hero_([a-z0-9]{8})", os.path.basename(p))
check(bool(m), f"basename shape wrong (want donut_hero_<8 base36>, no ext): {p}")

# 2. a scattered absolute path is reduced to its basename in the render_dir
p2 = s.resolve_render_path("/some/scattered/place/shot.png")
check(os.path.dirname(p2) == RDIR.rstrip("/"), f"absolute path not redirected: {p2}")
check(os.path.basename(p2).startswith("shot_"), f"basename lost: {p2}")

# 3. output_dir override wins, still tagged + extension-less
p3 = s.resolve_render_path("hero.png", output_dir="~/Desktop")
check(os.path.dirname(p3) == os.path.expanduser("~/Desktop"), f"override ignored: {p3}")
check(re.fullmatch(r"hero_[a-z0-9]{8}", os.path.basename(p3)), f"override basename wrong: {p3}")

# 4. empty/whitespace name -> 'render' fallback, never crashes
for bad in ("", "   ", None):
    pr = s.resolve_render_path(bad)
    check(os.path.basename(pr).startswith("render_"), f"empty-name fallback wrong: {pr!r}")

# 5. collision-free: same name twice yields different tags
a = s.resolve_render_path("x.png")
b = s.resolve_render_path("x.png")
check(a != b, "two resolves of the same name collided")

if fails:
    print("test_settings_render_path :: FAILED")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"test_settings_render_path :: PASSED — render_dir={RDIR}")
