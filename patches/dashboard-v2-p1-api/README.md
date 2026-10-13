# Apply Phase 1 in another clean checkout

The implementation already exists in `.worktrees/dashboard-v2` on
`feature/dashboard-v2-p1-api`, commit `7e6190752283dde7f8cfbda54d26a1705bce3e15`.
Do not apply the patch again there or in the main checkout with pending work.

Base: `b5b44854aec8b30b08ee3c8dbc43176807549a88` from the RFID branch, explicitly
authorized by DevX because origin/main does not contain the prerequisites.
The patch includes only dashboard Phase 1, not the RFID branch itself.

In a separate clean clone with this base available:

```powershell
git fetch origin
git switch -c feature/dashboard-v2-p1-api-import b5b44854aec8b30b08ee3c8dbc43176807549a88
Get-ChildItem 'C:\Users\DevX\Desktop\Coding\SentinelAI\patches\dashboard-v2-p1-api\*.patch' | Sort-Object Name | ForEach-Object { git am $_.FullName }
```

No push, merge or PR was performed. Validation: 63 passed, 1 optional vision
skip, real loopback HTTP checks passed, and the patch reverse-apply check
passed against the delivered commit. The isolated checkout is clean.

See `docs/dashboard-v2-review.md` for plan corrections and
`docs/dashboard-v2.md` for run commands and the API reference.
Per the supplied phase gate, the next step is Phase 2 (SSE), after DevX says go.
