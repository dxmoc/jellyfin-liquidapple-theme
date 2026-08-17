# LiquidApple

A Jellyfin theme built around Apple's Liquid Glass material: translucent panes
with refracted edges, specular rim light, capsule controls and iOS spring
motion. Dark only, and deliberately colourless — the artwork behind the glass is
what supplies the colour.

No JavaScript, no plugin, no fonts or images fetched at runtime. One CSS file.

## Install

Dashboard → **General** → **Custom CSS**, paste this and save:

```css
@import url("https://cdn.jsdelivr.net/gh/dxmoc/jellyfin-liquidapple-theme@main/dist/liquidapple.min.css");
```

`@main` tracks the latest commit. Swap it for a tag — `@v0.1.0` — to pin a
release and stop the theme changing under you.

Prefer not to route through a third-party CDN? The same file is on GitHub Pages,
which serves it as `text/css` too and updates on push:

```css
@import url("https://dxmoc.github.io/jellyfin-liquidapple-theme/dist/liquidapple.min.css");
```

Or skip URLs entirely and paste the contents of
[`dist/liquidapple.min.css`](dist/liquidapple.min.css) straight into the box.

> One thing that does **not** work: `raw.githubusercontent.com`. It serves
> `Content-Type: text/plain` with `X-Content-Type-Options: nosniff`, so the
> browser refuses the file as a stylesheet and the `@import` fails silently —
> no console error, just an unstyled Jellyfin. Gist raw behaves the same.

Custom CSS applies per-server to the web client and to any client that renders
the web UI. Native apps (Android TV, Roku, Swiftfin) do not read it.

## Customise

Every value the theme uses is a custom property. Redefine any of them *after*
the `@import` — no fork needed:

```css
@import url("...liquidapple.min.css");

:root {
  --la-accent: #0a84ff;        /* iOS blue instead of neutral white */
  --la-accent-text: #ffffff;   /* text on top of the accent */
  --la-blur: 30px;             /* thicker glass */
  --la-saturate: 140%;         /* calmer colour bleed through the glass */
  --la-refract-blur: 0px;      /* switch off the refracted edge */
  --la-mesh-opacity: 0;        /* switch off the ambient colour mesh */
  --la-login-bg: url("/web/assets/img/banner-light.png");
}
```

The ones worth knowing:

| Token | Default | What it does |
| --- | --- | --- |
| `--la-accent` | `#f5f5f7` | Fill of the single primary action per screen |
| `--la-blur` | `22px` | Glass thickness on chrome surfaces |
| `--la-saturate` | `180%` | How much colour the glass pulls through from behind |
| `--la-refract-blur` | `6px` | Strength of the refracted outer edge; `0px` disables |
| `--la-mesh-opacity` | `1` | Ambient colour mesh behind everything |
| `--la-ground` | `#06070a` | Page background |
| `--la-r-lg` / `--la-r-pill` | `22px` / `999px` | Card radius / control radius |
| `--la-lift` | `-4px` | How far a hovered card rises |
| `--la-login-bg` | `none` | Artwork behind the login card |

Full list with comments: [`src/00-tokens.css`](src/00-tokens.css).

## Fonts

The stack is `-apple-system` → `SF Pro` → `Inter` → `system-ui`. Apple hardware
gets SF Pro for free; everywhere else falls back to the system UI font. Nothing
is fetched from a CDN, on purpose. If you want Inter's proportions on
non-Apple clients, install it locally or add the `@font-face` yourself.

## Compatibility

Built against the Jellyfin **10.10 / 10.11** web client. Newer releases move
class names around occasionally; open an issue if something looks wrong.

Needs `backdrop-filter` (Chromium 76+, Safari 9+, Firefox 103+). Without it the
theme falls back to opaque surfaces automatically.

It also honours, without any configuration:

- `prefers-reduced-transparency` — Apple's own Reduce Transparency setting
- `prefers-reduced-motion` — no springs, no sheet animations
- `prefers-contrast: more` — stronger rims, brighter secondary text
- `.layout-tv` — solid surfaces and a loud focus ring, because stacked
  `backdrop-filter` layers are a slideshow on Android TV and Fire TV boxes

If the web client feels sluggish on a weak machine, set `--la-refract-blur: 0px`
first, then `--la-blur: 0px`.

## Develop

`src/*.css` is the source; `dist/` is generated. Filename prefixes are the
cascade order, so `99-fallbacks.css` must stay last.

```sh
python build.py     # writes dist/liquidapple.css and dist/liquidapple.min.css
```

Python 3.9+, standard library only. The version comes from `VERSION` — the one
place it lives — and is substituted into `__VERSION__` at build time.

To look at the theme without a running server, open
[`preview/index.html`](preview/index.html). It reproduces enough of Jellyfin's
markup and layout to judge the material offline. Its `<style>` block is
scaffolding standing in for jellyfin-web's own base CSS; the theme must never
depend on it.

## Licence

MIT. Structural cues for which selectors matter were taken from
[ElegantFin](https://github.com/lscambo13/ElegantFin); none of its CSS is used.
