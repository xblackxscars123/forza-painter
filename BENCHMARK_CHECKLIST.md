# Forza Painter Preset Benchmark Checklist

## Goal
Use the same test routine each time so profile comparisons are fair and repeatable.

## Test Set
- Pick 3 images at minimum: portrait, logo/high contrast, and busy scene.
- Keep source image files unchanged between runs.
- Use the same shape target and same Forza template each run.

## Run Procedure
1. Close background apps that consume heavy CPU.
2. Reboot once before a full benchmark batch if possible.
3. Run one warm-up generation before recording timings.
4. For each profile, process images in the same order.
5. Record elapsed time at 500, 1000, 2000, and 3000 shapes.
6. Save every generated json output for side-by-side review.

## Quality Scorecard
Score each output from 1 to 10:
- Edge fidelity
- Color accuracy
- Shape efficiency (fewer obvious redundant blobs)
- Overall readability at game-view distance

## Speed Scorecard
Capture:
- Total runtime to stopAt
- Time per 500-shape checkpoint
- Average CPU usage

## Decision Rule
- Daily-use profile: best average quality with acceptable runtime.
- Final profile: highest quality regardless of runtime.
- Keep both selected profiles and archive weaker candidates.
