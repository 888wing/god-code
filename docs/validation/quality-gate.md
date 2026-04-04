# Quality Gate

The quality gate is what turns God Code from “an LLM that edited files” into “an agent that attempted verification”.

## What It Does

Depending on the changed files and available tools, the quality gate can include:

- project validation
- script linting
- scene/resource checks
- consistency checks
- dependency analysis

## Why It Matters

A model saying “done” is not proof. A useful God Code result should surface:

- what changed
- what was validated
- what failed
- what still needs manual confirmation

## Read The Verdict Carefully

- `PASS`: validation passed for the checks that actually ran
- `PARTIAL`: useful output exists, but some evidence is incomplete or warnings remain
- `FAIL`: blocking issues remain and should be fixed before calling the change complete

## Best Practice

For the first few turns in a new project, prefer small requests that create clear, local validation outcomes. That makes the quality gate much more meaningful than asking for a huge feature all at once.
