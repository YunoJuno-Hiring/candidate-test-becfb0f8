
I started the task on Friday around other things I had on and completed it on Saturday. In total, probably about 4 hours. The first 1.5 hours was the baseline hardening and security work. The notes didn't call for that, but this is a "head of" role and it would be my responsibility to ensure that SDLC standards (data protection (*GDPR art. 28, 43*), Cyber Essentials, ISO 27001) and security policy duties are being met. To that end, I spent time doing it as that's part of the role - making judgment calls.

## AI usage & approach

I use Claude Code. I direct, it writes. I started off with a blank AGENTS.md file (Claude now supports that) and added to it as I went.

There was a time limit on this task so I leaned heavily into using AI for this, deciding that showing fuller features with approach was better than a limited feature set but delightfully terse and teeny pull requests. If this was a senior or staff position I'd have laid off the AI and gone more hand written and left out a lot of the security and quality gating. Zed with the inline models I really like.

However this is a "head of" role, and I wanted to show that it's OK to use AI, it's not always the most succinct, but it can produce perfectly functional code. Essentially, I wanted to set the lowest standard acceptable so that as a lead, there's a line in the sand from which to maintain quality.

I'm not going to be the best engineer on the team - if I was I'd be wasted in a "head of.." role, my skills are balanced over the full domain. I can engineer well enough to ship and I'm confident in my ability to ensure security, but I also need to lead and be responsible for ensuring quality, so this submission is a reasonable baseline of that.

So if you're looking for the best engineer on the team for this role - that's not me. I'm a generalist / polymath and my strength is the balance of skill I bring over all domains this role requires.

## What I built and why

### Choice: Task C

I've spent the last year delivering (solo) on a heavily async driven message queue integrating two state machines (Shopify via GraphQL) and a book distributor's enterprisey CSV / XML inventory and ordering system. That was in Elixir, Postgres, with Oban as a message queue and driven partially by Shopify's webhook system, deployed over AWS and fly.io.

Task C was a solid choice as the async nature of webhooks, task queues, idempotency etc. Also, React isn't something I've used in anger and so it's a good chance to show competency with AI in an unfamiliar language. I can poke React and I've built a small handful of things with it, but the AI is doing the heavy syntactic and pattern lifting.

I was a little conscious of the 5K lines of code and reactions to that. Here's the breakdown.

Note: I calculated these before I added this file.

| Stage                      | Code (+/-)      | of which tests | Lockfiles (+/-)  |
| -------------------------- | --------------- | -------------- | ---------------- |
| PR1 security baseline      | +212 / -18      | +33            | +1574 / -358     |
| PR2 quality gates          | +162 / -44      | +1             | +796 / -0        |
| PR3 webhooks backend       | +1411 / -24     | +708           | +91 / -1         |
| PR4 webhooks front end     | +565 / -53      | +137           | -                |
| PR5 tidy up & review fixes | +798 / -112     | +454           | +33 / -22        |
| **Total**                  | **+2992 / -95** | **+1319**      | **+2474 / -361** |
|                            |                 |                |                  |

And by area, as a share of the 5,466 lines added:

| Area                                         | Lines added | Share  |
| -------------------------------------------- | ----------- | ------ |
| Backend - function                           | 798         | 14.6%  |
| Backend - tests                              | 1,111       | 20.3%  |
| Frontend - function                          | 446         | 8.2%   |
| Frontend - tests                             | 198         | 3.6%   |
| Other (lockfiles, config, CI, migrations)    | 2,913       | 53.3%  |
| **Total**                                    | **5,466**   | **100%** |

Of the "other", 2,474 lines (45% of the whole PR) are generated lockfiles. The rest is config, CI, the pre-commit hook and generated migrations. Backend tests outweigh backend code.


### Security & Quality

I spent time hardening the baselines and generally reviewing the security of everything. Containers running as root, npm being used and packages with high and moderate vulns. They are the kinds of things that fail vendor security assessments so fixing them (and staying on top of them) as part of culture is just as important as feature development. Letting them slip and slide has a negative cultural effect.

What got upgraded:

* Python 3.11 > 3.14 (3.11 is next to reach end of life). The README brief still says 3.11, I left the brief as written.
* Django > 5.2.18 LTS, DRF > 3.18.3 and sqlparse > 0.6.0 to clear known vulnerabilities
* the webhook receiver moved off end-of-life Node 20 to Node 24, stopped running as root, and installs with pnpm from a lockfile (no npm)
* Mailpit pinned to v1.33 instead of an untagged latest
* front end dependencies updated within their ranges, clearing 20 of 22 audit advisories. The last 2 were cleared by upgrading React Router to 7.
* pnpm and uv both hold new package versions until they are 14 days old, so a compromised release has time to be caught before we pull it in

There were no front end tests or anything to verify the front end builds and is functional, so I added Vitest and a handful of tests. If this was a real app in the real world I'd add Playwright and have a full set of e2e tests.

I added an action to demonstrate that the codebase passes all the quality gates. There should always be automated quality gates.

Here's what is now done before any commit

 Preflight
  1. docker, task and pnpm are installed, and frontend/node_modules exists.

  Frontend

  2. Dependency audit: pnpm audit --audit-level high. Fails on any high or critical advisory.
  3. Tests: pnpm test (Vitest).
  4. Build: pnpm build, which runs the tsc typecheck and then vite build, so it catches type errors and broken imports.

  Stack

  5. docker compose up -d --wait, then waits up to 30s for Postgres to accept connections.

  Backend (task check, cheapest first)

  6. Lockfile in sync: uv lock --check
  7. Formatting: ruff format --check. New files only; pre-existing files are on the TODO exclude list.
  8. Lint: ruff check, with pycodestyle, pyflakes, import order, bugbear, modern syntax, simplifications, Django rules and Bandit security
     rules. Line length is 119.
  9. Dependency hygiene: deptry, which catches undeclared imports and unused dependencies.
  10. Types: mypy with Django and DRF stubs. Strict for the webhooks app, lenient for the rest.
  11. Django system checks: manage.py check --fail-level WARNING
  12. Missing migrations: manage.py makemigrations --check --dry-run
  13. Dependency audit: pip-audit --strict against the locked dependencies.
  14. Tests: pytest, with warnings treated as errors.

>  ℹ️  Note: at this point, if this wasn't constrained by "one pull request" I'd have made the work so far its own dedicated PR as it was essentially remedial technical debt of the type that often needs to be done before a customer's vendor security questionnaire is submitted or an external audit of some kind (ISO 27001 / SOC 2). It adds up to nearly 2K lines, but only about 230 of those are hand-written - the rest is regenerated lockfiles. Let's call this PR1

### Quality gates

Once the security baseline was established and before the main work started I wanted to make sure the quality gates were properly set up in the pre-commit hooks.

shameless blog post plug: https://jamiecurle.com/posts/my-quality-gates-for-shipping-ai-written-code. Obviously this is Python not Elixir but the premise stands.

Very conscious of a noisy PR, I didn't format existing files but rather added them into an exclude list. This is the kind of work that should be its own PR. Mixing formatting with features is asking for trouble over a certain volume.


Whilst working the agent found a thing:
- mypy found a real bug in the webhooks stub: a JSON list body would have crashed POST /api/webhook-endpoints/ with a 500, because a list
    has no .get(). A one-line guard fixes it.


> ℹ️ Note: this section of work would have also been its own PR and the reformatting of existing files left as chores to do when "you get five mins". This would have been PR2



### Choice of payload

Contract created - reason is legal. If a timesheet is submitted before a contract is created then performance of the contract could be argued to have started. That creates issues around terms and could open the platform up to claims around losses and breach of contract. So contracts before timesheets. It also keeps personal data out of the payloads. If I did have to implement an event that contained personal data then I'd send only an event id to the endpoint and then the consumer would call an endpoint on this system to hydrate the id into a full payload. (the thin payload pattern - privacy by design).


### Decisions around payloads & delivery

* WebhookPayloads are a basic state machine: created > queued > [delivered | failed], and failed > queued for retries.
* **POINT 1:** Async delivery - didn't want to bump Django to version 6 to get the builtin queue features, so brought in django-tasks, the backport (with django-tasks-db as the Postgres-backed queue - Django 6 only ships test backends, so it would have needed that anyway). I was tempted by Oban as I've been using that heavily in production on an Elixir app for the last year and it became available in Python recently. However, that's the kind of thing for personal time. Keeping things predictable and operational is a part of maintaining a solid platform.
* Failures retry with a capped back off (WEBHOOK_RETRY_DELAYS): 1m, 5m, 15m, 1h, 2h, 4h, then every 8h, with ±10% jitter. After 7 days it gives up and disables the endpoint. Admins are emailed once per incident after the 4th failed retry.
* At least once delivery. Consumers can dedupe webhooks on the id as this remains constant over retries and sends.
* When a disabled or paused endpoint is re-enabled only the most recently saved event is queued for sending.
* Pausing an endpoint stops everything, including deliveries already queued or waiting to retry - they fail for good with "Endpoint is not active". A disabled endpoint still accepts test events, as a successful one is how it gets re-enabled.
* Secrets are only shown once - at creation time. They can be rotated and my design keeps a current and previous secret for 24 hours, so receivers have time to switch to the new secret without failed deliveries - while both are live every delivery carries a signature from each.
* A failed delivery doesn't fail the worker job - it's recorded in the delivery log and the retry is queued as a new job. I considered failing the job, but django-tasks would log a full traceback for every failed attempt (about 27 for a receiver that's down for a week) and "their server is down" would look the same as "our code crashed". Good discussion point.
* Payloads are signed with the Standard Webhooks HMAC-SHA256 pattern (`v1,WOTIahylNQuf92CKHVEIzW6TIseG3R6E8Gi6J1Y+TLw=`)
* the headers carry the signing information - webhook-id, webhook-timestamp & webhook-signature
* each delivery attempt records the URL it was actually sent to, so the audit trail survives someone changing the endpoint URL later
* the payload is structured and versioned (**POINT 5**) as below. This makes the path to altering payloads trivial. The version is a setting (WEBHOOK_PAYLOAD_VERSION) so dev can run ahead of prod. I didn't do a JSON schema and test contracts in this app. It's a "thin" payload - the download link is a deliberately fake placeholder for a short-lived signed link to the contract PDF.

```
{
    "id": "evt_60ffa21ec6424827820cd649f8492b58",
    "type": "contract.created",
    "version": 1,
    "created_at": "…",
    "data": {
      "id": 42,
      "status": "active",
      "start_date": "2026-06-01",
      "end_date": "2026-12-31",
      "download_url": "https://fake-bucket.examplecloud.com/fake.pdf?signature=fake"
    }
  }
```



### If it was prod and a real world feature

1. Secrets aren't encrypted in this app. If it was production they would be but given there's no default package for encryption, I didn't want to add a package for this specifically.
2. If this was prod, I would have matched whatever queue you had there, but I didn't know that when I was designing. My default go-to in Python world is Celery and RabbitMQ but that's overkill for this. This way we get retry and async sending which imho is essential to this type of feature if you need to design where you scale the system.
3. If gettext was being used for translations, I would have wrapped everything in that, but as this is an example, I didn't. Retrofitting I18N is a chore so best to stay on top of it.


>  ℹ️  Note: at this point, if this wasn't constrained by "one pull request" I'd have made the work so far its own dedicated PR. I'd be looking to make sure it went incident free and the migrations applied and there was no drama. This would have been PR3. If we were doing feature switches, this is where we'd do the dark launch for internal testing. Alpha release.


### Front end

I really haven't used TypeScript or React in anger that much. I tend to pick a thing and stick to it (Django 2006-2020 then Elixir 2019-now) and wanted to do this task as it gave me a chance to use AI for this using TypeScript and React. I kept the UI to two pages.



>  ℹ️  Note: at this point, if this wasn't constrained by "one pull request" I'd have made the work so far its own dedicated PR. I'd be looking to make sure it went incident free and the migrations applied and there was no drama. This would have been PR4. If this was a real feature deployment, this would be where we'd open it up to everyone or select users. Beta release.


### tidy up

* tests missing on tasks.py - added those
* standard Django pattern stuff - moved any CONSTANTS to settings. Updated the AGENTS.md to reflect that
* added an .env.example file - small things like this can smooth people's onboarding and make for easy "first PRs" for new team members.
* A full security scan and code review by the AI - fixed these:
	* high: Pausing didn't stop deliveries that were already queued or waiting to retry
	* high: Unexpected exceptions left payloads stuck in "queued" forever, and an out-of-range port caused a 500
	* med: Destination response bodies were read in full. Caught a buffer that would have allowed GBs into memory, so switched to a stream which ensures we don't inflate memory by buffering responses we don't need to read. It reads raw bytes, so a gzip bomb can't get round the cap either.
	* med: the contract download link pointed at a route that doesn't exist - now an obvious placeholder
	* med: the payload's URL was saved but never used - each attempt now records where it was actually sent
	* low: N+1 on the endpoint list: get_last_delivery ran one query per endpoint, so N endpoints meant N+1 queries. It's now 2, however many endpoints there are, with a test that fails if it ever creeps back.
	* low: a stale worker could schedule a second retry chain - now it stops if another worker already recorded the outcome
	* low: the "URL saved" message never showed, and the local test URL needed a setting that's now in .env.example
	* moved common queries into "manager" classes and updated AGENTS.md to reflect that. The models file is now borderline for splitting up into a dedicated `managers` module, left as is.


### remaining review points

I left one as discussion.

* med: SSRF hardening / DNS rebinding - what is your approach to this kind of attack?

>  ℹ️  Note: at this point this would be the final PR before going public with the feature. General availability. This would be PR5 and if you're using semantic versioning a minor bump.



And that's where I left the task. 

Over to you.

Cheers,

Jamie.