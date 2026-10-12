# WalletLens: submission pack

Replace every YOUR-URL with the live Render link. Only keep a claim if it is true on the day you submit.

## Project name
WalletLens

## One line
Read-only token-approval scanner and pre-sign check API for Monad: see who can spend your tokens, with a link to the transaction behind every finding.

## Short description (form field)
WalletLens reads a Monad wallet's full ERC-20 approval history through Envio HyperSync, keeps the approvals that are still active, groups unlimited allowances by spender, and returns structured findings. Every finding links to the on-chain transaction that created it. A public read-only API lets wallets and dApps run a pre-sign check on a spender before asking the user to approve. WalletLens never asks for keys or signatures, and it never says a wallet is "safe".

## Long description
**Problem.** A token approval is a permission that stays open until it is revoked. Most users cannot see which contracts can spend their tokens, and apps have no simple way to ask whether a new approval is worth a warning.

**What we built.** (1) A scanner that covers the wallet's whole history on Monad via Envio HyperSync. (2) A rule engine that groups findings by spender. "High" is reserved for an unlimited approval to a plain wallet (no contract code); an unlimited approval to a contract is "worth reviewing", because trading apps commonly request it. (3) A versioned public API: `/api/v1/scan/{address}` and `/api/v1/check?spender=...`, documented at `/developers`. (4) Findings are structured: id, severity, title, description, evidence, source, confidence, limitations.

**Trust and safety choices.** Risk is shown as a category, never an invented score. Text from the chain is never fed to the AI model and is rendered as plain text. Keys stay on the server. The README and the page state what is not checked: NFT approvals, token reputation, known-malicious address lists, balances, and transaction history.

**Why a primitive, not just an app.** Any wallet, dApp or bot can call the check endpoint in a few lines, so the trust layer is shared instead of rebuilt by every team.

## Track and bounties
- Primary track: Trust, Identity & AI Infrastructure.
- Bounties: **Envio** (HyperSync is the core data layer). **Kimi** only if the explanation text on the live site says "AI-written"; if not, do not select it.

## Answer to "why not Revoke.cash?"
Revoke.cash is a mature tool for revoking approvals. WalletLens is different in two ways: it is a Monad-first API other apps can call (including a pre-sign check), and it explains findings in plain language with evidence links. We do not claim to replace it.

## Message to send builders (for the traction quote)
> Hi! I built WalletLens for Metropolis: paste a Monad wallet and it shows who can spend its tokens, with a link to the transaction behind each finding. Could you try it for 2 minutes at YOUR-URL and tell me (a) what was unclear and (b) one line I can quote? There is also a small API at YOUR-URL/developers if you are building a wallet or dApp. Thanks!

Use at most 3 quotes, word for word, with the person's permission.

## Technical demo video (max 3 minutes, live product, no slides)
1. **0:00-0:15** Say what it is. Open YOUR-URL.
2. **0:15-1:15** Paste the demo wallet `0x0926f95b2e774804894e8d531823301578632342`. Show the report: risk label, one grouped finding, the analysis. Click "View the transaction" and show it on the explorer.
3. **1:15-1:45** Paste a wallet with no findings. Point out the wording: "does not prove the wallet is safe".
4. **1:45-2:30** Open `/developers`. In a browser tab or terminal, call `/api/v1/check?spender=...` and show the JSON verdict.
5. **2:30-3:00** One sentence on Envio HyperSync (full history in seconds), and the limits you state openly.

Record at a normal pace, open the site a few minutes before recording (the free host sleeps), and scan the demo wallet once beforehand so repeat scans are cached.

## Pitch video (max 2 minutes, introduce the team)
- **0:00-0:20** Names, roles, one line about each of you.
- **0:20-0:50** The problem: approvals stay open, users cannot see them, apps cannot easily check them.
- **0:50-1:20** The solution: scan plus pre-sign API, evidence on every finding, never "safe".
- **1:20-1:45** Why it should be shared infrastructure, and who would call it (wallets, dApps, bots).
- **1:45-2:00** What is next: more checks (NFT approvals, known-bad lists), and your real plan to get integrations after the event.

## Final checklist
- [ ] Live URL opens on a phone over mobile data
- [ ] Scan of the demo wallet works; the transaction link opens the right transaction
- [ ] Repo is Public and contains no `.env`, no keys
- [ ] README and `/developers` have the real URL
- [ ] Logo uploaded (`logo/walletlens-logo.png`, under 3 MB)
- [ ] Demo video link, pitch video link
- [ ] Track and bounties chosen on the Metropolis project page
- [ ] Progress update posted
- [ ] Submitted at least 12 hours before 14 Oct 09:29 IST, then re-opened to confirm it saved
