# CodeCatalog

Coded screens, kept as a library to lift into the folio. Every screen here is live HTML and
CSS, never a picture of one. One collection so far: Penfold, 11 desktop and 13 mobile.

The catalogue page is `index.html`, served straight from `main` on
GitHub Pages at https://cesarxdesign.github.io/CodeCatalog/. Every push to `main` updates it
within a minute. (It was also on Vercel until 2026-09-25; that project is deleted.) The old claude.ai artifact is retired; do not publish there.

## Where the latest lives

This folder, on `main`, is the only latest, and the link above is served from it, so the
two cannot drift. Screen names come from each screen's `meta.json`; to rename a screen, change
it there and push.

Top level holds only: README, BACKLOG, `catalog.json`, `index.html`, `screens/`, `tools/`,
`figma2code/`. Anything else is out of place.

## Before trusting it

    python3 tools/check.py

About 40 seconds. Proves every screen still works rather than assuming it: metadata complete,
every file present, built outputs current, no paths tied to this machine, fonts loaded, and
all 38 pages (each embed and each screen) rendered in headless Chrome with no script errors.
Exit 0 means usable. It has been run against deliberately broken copies and catches each fault.

## Getting a screen out

Start at `catalog.json`. One entry per screen, with `id`, `name`, the on-screen `title`,
`aliases`, `frame`, `fonts` and every file path. Match a request like "the standing order
screen" or "you're all set" against those, then take the files from the screen's folder.

    screens/<project>/<platform>/<id>/
      embed.html     use this on the folio. Style-isolated (shadow DOM), so it cannot collide
                     with the page it lands in, and it loads exactly the fonts it needs.
                     Scale it:       .cc-screen{--cc-scale:.5}
                     Background it:  .cc-screen{--cc-bg:#F6F6F6}
                     No scripts: an interactive screen embeds as one fixed state.
      screen.html    the standalone page. The clickable version where there is one.
      meta.json      everything known about the screen. The only file to hand-edit.
      source/        what it was built from.
      state-*.html   fixed states of an interactive screen, where they exist.

A key is `project/platform/id`, e.g. `penfold/desktop/monthly-payment`.

**Put embeds in the HTML itself.** If the folio inserts one with JavaScript, use
`element.setHTMLUnsafe(html)`. Never `innerHTML`: the shadow root does not attach and the
screen renders blank. Both verified in Chrome.

## The screens

**Desktop**, rebuilt from raster exports

| id | name | frame | |
|---|---|---|---|
| `three-things` | 3 things about pensions | 1231×2640 | clickable · all closed, any section open |
| `plan-selection` | Plan selection | 1182×2640 | clickable · plans, risk, accept |
| `savings-calculator` | Savings calculator | 1182×2640 | clickable · 1, 2, 3, 4 |
| `sign-up-form` | Sign-up form | 1182×2640 | clickable |
| `monthly-payment` | Monthly payment | 1182×2640 | static |
| `document-consent` | Document consent | 1182×2640 | static |
| `enter-email` | Enter your email | 1182×2640 | static |
| `sign-up-upper` | Sign-up, upper half | 1182×2640 | static |
| `savings-path` | Savings path | 1182×2640 | static |
| `standing-order` | Standing order | 1182×2640 | static · + Roboto Mono |
| `confirmation` | Confirmation | 1182×2640 | static |

**Mobile**, read from the Figma file

| id | name | frame | |
|---|---|---|---|
| `home` | Home | 375×812 | static |
| `pause-resume` | Pause & resume | 375×812 | static |
| `payment` | Payment | 375×812 | static |
| `growth` | Growth | 375×812 | static |
| `login` | Login | 375×812 | static |
| `combine` | Combine | 375×812 | static |
| `beneficiary` | Beneficiary | 375×812 | static |
| `transactions` | Transactions | 375×812 | static |

**Mobile · onboarding flow**, read from the Figma file with the `figma2code` skill, node values
taken from the Plugin API

| id | name | frame | |
|---|---|---|---|
| `eligibility` | Eligibility | 375×812 | static |
| `onboarding-first` | Onboarding first | 375×812 | static |
| `onboarding-next` | Onboarding next | 375×812 | static |
| `details` | Personal details | 375×2329 | static · long form |
| `onboarding-final` | Onboarding final | 375×812 | static |

Clickable desktop screens have a `live` URL in their meta.json: plan-selection,
savings-calculator, sign-up-form, three-things. Static ones have none, because the embed
already shows all of them. Mobile screens link to the Figma-vs-code comparison.

## Every state is a tile

A desktop screen with more than one state shows each state as a tile of its own on the catalogue page,
right after the screen: 3 things about pensions (all closed, and states 1 to 6 from `states.html`),
Plan selection (risk levels, risk acceptance), Savings
calculator (steps 1 to 3; the screen's own tile is step 4) and Document consent (all four documents
open, from `state-expanded.html`). Sign-up, upper half has one variant made for the folio,
`state-with-email.html`: the email screen folded in as a field, before the password. 24 desktop views from 11 screens.
Plan selection's `state-choose.html` and `state-risk.html` stay in its folder but have no tile:
they repeat the plans and risk-levels states.

Document consent's open view has no source picture. Only the Penfold Terms copy comes from the export;
the text under the other three documents is placeholder, written to differ in length.

They come from `"views"` in the screen's meta.json. Each has an `id` and a `name`, and any of `from` (the
file), `state` (`[attribute, value]` set on `.page`), `pane` (one `<section class="v-pane">` of a page that
holds several) and `frame`. `tile` names a tile after its step in the first onboarding flow ("3 things 05") and
`seq` is its place in that flow; desktop tiles run in `seq` order. Both can sit on the screen itself too.
Steps with no tile (13, 14, 18, 21, 22, 25 to 30) are states that were never built. A view's key is the screen's key plus `@id`, e.g.
`penfold/desktop/three-things@state-3`. catalog.json lists them under each screen's `views`.

## Projects and flows

The catalogue page filters by **Project** and **Flow** (two dropdowns in the left pane, which holds the header, the controls and the grid of screens; the right pane shows the selected screen, code only unless Show source is on, with the notes beside it when Show bento is on). Both
come from each screen's meta.json: `project` is required, `flow` is optional - a screen with no
flow shows under "All flows" only. A new project or flow appears in the dropdowns on the next build.

A screen can sit in more than one flow: `flow` is then a list, e.g. `["master-combine", "closer"]`.
`seq` is the screen's place in its flow, and with one flow picked the grid runs in `seq` order.
It is a number, or `{"closer": 6}` when the screen's place differs from flow to flow. The
`closer` flow is the Penfold grid (Figma node 92:18503) that closes the case study, in the grid's
reading order.

The current view lives in the URL, so a filtered view can be bookmarked or shared:

    index.html#project=penfold&flow=onboarding
    index.html#flow=onboarding&screen=penfold/mobile/details
    index.html#show=mob&source=1&bento=1&screen=penfold/mobile/home

## Changing things

    edit a screen.html or meta.json
    python3 tools/build.py            regenerates embeds, catalog.json, index.html
    python3 tools/check.py            must end OK
    commit and push; the link updates within a minute
    if the screen is clickable: republish its screen.html to its `live` URL too

Adding a screen: a new folder with `screen.html`, `source/` and a `meta.json` shaped like its
neighbours (`order` sets its place), then build and check. A new project folder works the
same way, but the catalogue page's group labels ("measured from pictures", "read from the
Figma file") describe Penfold and will need editing in build.py.

Needs python3, Google Chrome (check.py) and macOS `sips` (preview thumbnails, cached in
`.cache/`, gitignored). Freshness is judged by content fingerprints, not timestamps, so a
copy or a git clone does not look stale.

## Layout

    code     tools/build.py, tools/check.py
    source   screens/**/source/          exports and Figma renders, as supplied
    derived  screens/**/screen.html, state-*.html, states.html, snippet.html, meta.json
    out      screens/**/embed.html, catalog.json, index.html    built, never hand-edited
    work     figma2code/onboarding/      the build that produced the five mobile onboarding screens
             figma2code/dashboard/       the Dashboard pair (desktop, mobile, ref), built, not yet imported

## The shared desktop shell

Squared up against the most accurate screen, three-things, and checked against source at
each step. Where a shared value landed far from what the export showed, the export won.

- Frame 1182 × 2640. Column at x 183, measure 770. Heading top 92.
- Montserrat. H1 49px/57px, -0.9px tracking. Body 19.4px/29.5px, paragraphs 23px apart.
- Navy `#133253` for headings and body copy alike. Pink `#ED5E83`.
- Each screen's internal spacing is as measured; screens were shifted whole to the shared
  heading line, never re-spaced inside. Form rows keep their own rhythm.

Exceptions, both source-backed: **three-things** keeps its own 1231 frame and 1062 measure,
and **confirmation** centres on the shared column (568) rather than its export's 604.

## Things that will trip you

- The exports are crops of the Figma canvas with arbitrary top edges. They say nothing about
  where a frame starts, so the heading line is a decision, not a measurement.
- The desktop set was first built in **Figtree**, a fitted guess. It is Montserrat: three
  headings measured against both land within 1.4% in Montserrat and 9-19% narrow in Figtree.
  The old sizes had been inflated about 12% to fake the width.
- standing-order also uses **Roboto Mono** for account numbers; its embed loads it.
- The mobile status bars use `-apple-system, 'SF Pro Text'`: Apple's system face on Apple
  devices, plain sans elsewhere. Deliberate - SF Pro cannot be served as a web font.
- A `#id` selector cannot hold the `/` in a key. Look sections up with `getElementById`.
- Renaming on the page (click the name at the top right of the preview) only changes names in the browser you typed them in. Real names are the
  `name` in each meta.json, in git. No names were ever saved in the old artifact's database.

## History

Built 2026-09-20 and 21 in one Claude Code session, with the `image2code` skill
(`~/Claude/skills/image2code`) for the desktop set and the Figma API for mobile. Moved here
from `Portfolio/Penfold/new/CodeScreens`, which was never committed.
