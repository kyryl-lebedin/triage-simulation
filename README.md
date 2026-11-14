# Triage simulation: handover

Built at DurHack 26. This is where the project stands and how we see the demo.

## What we are building

A platform where **synthetic AI participants** stand in for a real audience. You give it the thing you want to test, describe who the audience is, say what they are able to do, and run it. You get back which version did better, for whom, and **why**.

It has to work for any scenario, not one domain. **YouTube is the demo case**: we compare different intros for the same video.

## Where things stand

- **Done:** a clickable UI prototype of the whole flow, in `index.html`. Open the file in a browser; there is nothing to install or build.
- **Not started:** the simulation itself. Nothing calls an LLM. Every number on the results page is fixed demo data.

The prototype's product name, "Stand-in", is a placeholder.

## How we see the UI for the demo

Five pages, in order. The first three are the creation stages, each opening with a one-line prompt telling the user what to do.

| Page | Address | What the user does |
|---|---|---|
| 1. Material | `index.html#/dataset` | Names the scenario, picks the kind of material (YouTube video, ad copy, product page, blank), and adds the versions to compare. Versions can be renamed, reordered and removed. |
| 2. Participants | `index.html#/profiles` | Sets how many participants, then the audience mix for each variable (gender, age, region, plus custom ones like "owns a pet"). Each variable is one bar whose dividers you drag; it always totals 100. An empty variable can be filled by AI. Below that is the prompt each participant receives, with placeholders for the variables, and a preview of one participant. |
| 3. Actions | `index.html#/actions` | Presses in the actions a participant may take (like, dislike, comment, save, replay and so on), adds custom ones, and picks the main metric that decides the winner. |
| 4. Run | `index.html#/run` | Checks a summary of the setup and runs it. |
| 5. Results | `index.html#/results` | Sees each version's score on the main metric, the spread of every action, a split by any participant variable, and notes explaining why, with participant quotes. |

### The look

We tried several directions and chose this one, called "Tactile, compact":

- Flat colour blocks (cobalt, tomato, mustard) on a pale warm ground, with ink outlines and hard offset shadows.
- Everything is something you grab or press: drag-to-resize bars for distributions, press-in tiles for actions.
- Compact sizing, so more fits on a screen (standard buttons are 36px tall).
- Very little text.

Keep this look when building on it.

### The demo story

Channel "Slow Miles", video "We hiked 400 miles with a rescue dog", 500 synthetic viewers, three intros:

| Version | Intro | Kept watching past 30s |
|---|---|---|
| A. Cold open | Starts mid-storm, no preamble | 71% |
| B. Story first | Opens with their previous dog dying last year | 58% |
| C. Payoff tease | Shows the summit first | 64% |

The point the demo makes is the "why": B loses because pet owners disliked it (16% against 4% of non-owners), saying the dog's death in the first 15 seconds was upsetting. The same intro also got the most comments, from viewers who stayed and shared their own stories.

## What is fake or rough

- **Results do not react to the setup.** Changing the audience mix does not change the numbers. Versions, actions and variables you add yourself get made-up numbers.
- **"Fill with AI" is a timer** that drops in preset numbers.
- **Nothing is saved.** Reloading the page resets everything.
- **Two drag gestures are untested:** reordering versions by the grip, and dragging a placeholder into the prompt. The button and click versions of both work.
- **Fonts load from Google Fonts**, so offline it falls back to a plainer system font.
- The compact sizing sits as a block of overrides at the end of the stylesheet in `index.html` and has not been folded into the rules above it.

## What comes next

1. Build the simulation: generate participants from the distributions, send each one the prompt and a version, and collect their actions and reasons.
2. Replace the fixed numbers on the results page with real output, including the explanations.
3. Make "Fill with AI" a real call.
4. Decide whether to keep the single HTML file or move it into a framework once there is a backend.

## Repo notes

- `index.html`: the prototype. `CLAUDE.md`: the project aims, read by Claude Code sessions.
- Work on a branch and merge into `main`; avoid two people editing the same file.
