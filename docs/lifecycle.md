# Lifecycle Model

This substrate uses a scalable three-stage and three-pass model.

## Stages

1. `local`: run from local developer environment first.
2. `hosted_dev`: validate on hosted development environment next.
3. `production`: promote only after previous stages succeed.

## Passes

Each stage should carry the same ordered passes:

1. `research` (evidence and source validation)
2. `development` (implementation)
3. `testing` (verification and acceptance)

The pass sequence is tracked in run metadata; stage ordering is enforced by policy.

## Policy configuration

`workspace.yaml` controls this behavior:

```yaml
policy:
  enforce_stage_flow: true
  stage_sequence: [local, hosted_dev, production]
  pass_sequence: [research, development, testing]
```

This keeps the workflow lightweight early and ready to scale for broader project usage.

