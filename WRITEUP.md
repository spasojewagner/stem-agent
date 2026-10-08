# Write-up

<!--
Fill this in after running the experiments, in your own words. Keep it
honest and mid-length: what came out, what lifted results, what didn't
work, what you took from it. No polishing pass.
-->

## What I took "stem agent" to mean

<!-- Your answer to: what does "by default not specialised" mean for the
starting state, and where is the line between evolving inside a frame and
picking the frame. DESIGN.md has the decisions; say why you hold them. -->

## Setup

<!-- Models used, date, number of generations per environment, tokens spent
(each `grow` prints them, and runs/<env>/generations.jsonl has per-generation
numbers). -->

## Results

### Baseline (undifferentiated, held-out tasks)

| exchange | codeaudit | archive |
|---|---|---|
|  |  |  |

### Development, per generation (training score)

<!-- python -m stem show --run runs/<env> prints this table. -->

### Differentiation matrix (held-out tasks)

<!-- paste runs/eval/matrix.md -->

## What each genome became

<!-- `python -m stem show --run runs/<env> --code`. Quote its identity, list
the tools and skills it wrote, and point at the generation where the score
moved. -->

## What worked

## What didn't

## What I would do next
