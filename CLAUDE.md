# Project aims

Built at DurHack 26. This file records what we are building so every session and every UI version works towards the same thing.

## What the platform is

A platform where **synthetic AI participants** simulate how a real audience would react to something. The user sets up a scenario, customises the participants, runs the simulation, and gets results that show **which variable performs better and why**.

The platform must be **generalisable**: scenarios, participant variables and actions are all user-defined, not hard-coded to one domain. YouTube is only the demo example.

## The user flow

1. **Create a scenario.** The user names and describes what is being tested.
2. **Upload the material.** A dataset or a set of scenario variants. In the YouTube demo this is different versions of a transcript, an intro, or similar, to be compared against each other.
3. **Define the participants.** The user enters whatever variables they have about the audience, for example:
   - gender split (e.g. 60 percent female viewers)
   - age categories to target or consider
   - geography (e.g. North America is X percent of viewers)
   - anything else the user can specify

   Where the user has no data, an **LLM can help fill it in** (e.g. typical demographic distributions for a set of countries).
4. **Define the actions.** What a participant can do in response, again entered by the user. In the YouTube demo: like, dislike, comment, save, replay, and other interactions.
5. **Run the simulation** with the parameters above.
6. **Read the results dashboard.**

## The results dashboard

For each variable and each variant, the dashboard shows:

- **The spread of outcomes** on the main metrics (e.g. 10 percent of participants liked it), broken down by participant variable so the user can compare groups and variants.
- **An explanation of why**, summarising the participants' reasons (e.g. "many participants disliked the video because the opening story about a dog dying upset them").

The point is not only the numbers but the reasons behind them: the user should come away knowing why one variant or one audience segment did better than another.

## Current focus

- A **generalisable UI** covering the flow above: scenario creation, upload, participant variables, actions, run, dashboard.
- **YouTube is the demo case.** Use it for example data and copy, but do not bake YouTube-specific assumptions into the structure.
- **The chosen UI base is "Tactile, compact"**, in `index.html` on branch `ui-v3` (folder `triage-ui-v3`). It is a single self-contained clickable prototype with fixed demo numbers and no real simulation behind it. Build on this; keep its look (flat colour blocks, ink outlines, hard offset shadows, drag-to-resize distribution bars, press-in tiles) and its compact sizing.
- Branches `ui-v1` and `ui-v2` hold rejected directions and can be removed.

## Team workflow

- Nobody commits straight to `main`; work on a branch and merge small and often.
- Split work by file or folder so two people are not editing the same file.
- Say so in chat before touching shared files (dependencies, config, shared types).
