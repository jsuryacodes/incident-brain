# Demo & recording checklist

Grows as we build. Run top to bottom before recording the demo video or showing judges.

## Before every recording / live demo
- [ ] Docker Desktop open, `docker start falkordb`.
- [ ] **Re-seed:** `python -m seed.load --graph kestrel_pay --reset`, then `python -m seed.verify --graph kestrel_pay` → 13/13 PASS.
      All seed times are relative to load time ("risk-rules deployed 40 min ago"). Check 5 and 10 use a 2-hour window, so start recording within ~1 hour of seeding.
- [ ] Confirm no leftover agent memory from rehearsals: `MATCH (n {origin:'agent'}) RETURN count(n)` → 0 (the reset handles this).
- [ ] Product agents use `claude-sonnet-5-5` for the recording (Haiku during dev).
