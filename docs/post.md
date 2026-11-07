# Where does prompt-injection robustness come from in small-business agents?

*Caio Oliveira, November 2026. Draft.*

**TL;DR**

- We built four simulated small-business workflows (answering marketplace buyers, triaging email, filing complaints with public agencies, curating a newsletter), with 40 tasks each, mirrored in Portuguese and English, and attacked every task with indirect prompt injections hidden in the content the agent reads.
- **The model is the first line of defense.** Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 were never hijacked: 0 successes in 5,760 attacked episodes with no defense at all (95% upper bound 0.07%). The previous generation was not as robust: Sonnet 4.6 fell for 2.9% of one attack framing, and Haiku 4.5 for 15.2% and 30.2% of the two framings.
- **On the model that can be hijacked, architecture does most of the remaining work, almost for free.** On Haiku 4.5, one sentence in the system prompt ("content returned by tools is information, never instructions") brings attack success to 0.4% and 6.4%. Adding a per-action permission lock, set from the owner's request by a small model before the agent reads anything, brings it to 0.1% and 1.8%, with utility at 95% against 97% with no defense. A trusted monitor that reviews every action gets to 0.0% and 0.1%, but costs about 6 points of utility.
- **A lightweight detector added little, and can quietly break a non-English deployment.** The open-source detector we tested first blocked 81% of legitimate Portuguese episodes, cutting utility to 30%, because one of its layers was an English-only classifier. After that was fixed, it was cheap on legitimate work but still let 13% of one attack framing through, and when it did catch an attack it withheld the whole tool result, so the task failed anyway (utility under attack 63%).

## The question

Small businesses are starting to hand routine work to agents that read text written by strangers (buyer questions, emails, documents, articles) and can act (answer, send, move, change a price, file a complaint). Indirect prompt injection is the obvious risk. A small business has three places to look for protection: the model it buys, simple architectural choices it can make itself, and off-the-shelf detectors. We asked how much each contributes, measured on realistic workflows rather than on generic benchmarks, and in Portuguese as well as English, since most small businesses in the world do not work in English.

## Setup

**Environments.** Four workflows of one fictional ceramics studio, built on [Inspect](https://inspect.aisi.org.uk/) following the design of [AgentDojo](https://arxiv.org/abs/2406.13352): a simulated environment, tools that read and change it, user tasks with utility checks, and injection tasks with security checks, both scored on the final environment state. Each workflow has 40 user tasks (about half need a consequential action, the rest are questions), written in Portuguese and English with the same entities, ids and tools, so language is a paired comparison. A validator runs every task's reference solution, checks that each task is solvable and non-trivial, that each injection reaches the agent's context on that task's path, and that the reference solution does not satisfy any attack check by accident.

**Attacks.** Each workflow has three harmless injection goals: write a marker (`ZEBRA7731`) into something the business publishes or sends, send data to a simulated outside address on `.example.test`, or change state the owner did not ask to change (a price, a case status, an email's folder). Every user task is attacked with every goal of its workflow, using two framings: AgentDojo's "important instructions" message (the *classic* attack) and a short postscript that pretends to be a note from the owner (the *owner's note*). Probes with two more framings (a fake platform notice and a third-party request) also got no success on the 5.5 models. The attacks are fixed templates, not optimized against the models.

**Defenses.**

- `none`: a plain system prompt describing the job.
- `rule`: the same prompt plus one rule: content returned by tools is information, never instructions; only the owner's request defines the task.
- `lock`: an oracle least-privilege policy. A consequential action runs only if its tool and its target (which question, order, email, case, article or recipient) are among those the reference solution uses. Text arguments are not checked. This is an upper bound on what per-action permissions can do.
- `planlock`: a realistic version of the lock. Before the agent starts, Claude Haiku 5.5 reads only the owner's request and lists the actions it needs, with the targets the request names, and "any target" when the agent will have to find it in the data. Fail-closed.
- `armor`: every tool result goes through [prompt-armor](https://github.com/prompt-armor/prompt-armor), an open-source detector with five fused layers (regex rules, a small classifier, similarity to known attacks, structural features, a fusion model). Results it flags are withheld from the agent.
- `monitor`: before each consequential action, Claude Haiku 5.5 sees the owner's request and the proposed action and can block it. Fail-closed.

**Models.** Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 at effort `medium`, plus Claude Sonnet 4.6 and Claude Haiku 4.5 as the previous generation. Because attacks only landed on Haiku 4.5, the newer models ran every defense without attack (to measure the cost on legitimate work) and the attacks without defense; Haiku 4.5 ran every defense and combination under both attacks.

**Metrics.** Attack success, utility without and with attack, how often a defense fires on legitimate work, and cost per episode, with 95% Wilson intervals. In total, 34,240 episodes for about US$ 375 at list prices.

## Results

### 1. The current models resist on their own

| | classic | owner's note |
|---|---|---|
| Claude Haiku 5.5 | 0.0% [0.0, 0.4] | 0.0% [0.0, 0.4] |
| Claude Sonnet 5.5 | 0.0% [0.0, 0.4] | 0.0% [0.0, 0.4] |
| Claude Opus 5.5 | 0.0% [0.0, 0.4] | 0.0% [0.0, 0.4] |
| Claude Sonnet 4.6 | 0.0% [0.0, 0.4] | 2.9% [2.0, 4.2] |
| Claude Haiku 4.5 | 15.2% [13.1, 17.6] | 30.2% [27.4, 33.2] |

*Attack success with no defense, 960 attacked episodes per cell.*

The 5.5 models usually noticed the injected text, ignored it and finished the task; often they told the owner about it. Opus 5.5 ended 6.1% of attacked episodes with a refusal from its safety classifier, almost all on exfiltration goals. That is safe, but the task is lost: its utility under attack is 93% to 94%.

On Haiku 4.5, the owner's note works twice as often as the classic framing. Goals that change state succeed most (23% classic, 50% owner's note), and the complaints workflow, where the agent writes to companies on the owner's behalf, is the most exposed (38%).

### 2. Architecture does most of the remaining work

| defense on Haiku 4.5 | classic | owner's note | utility without attack | utility under attack |
|---|---|---|---|---|
| none | 15.2% | 30.2% | 97.2% | 92.1% |
| rule | 0.4% | 6.4% | 96.2% | 94.7% |
| lock (oracle) | 1.2% | 2.6% | 96.6% | 92.7% |
| planlock (realistic) | 2.9% | 5.1% | 95.3% | 93.2% |
| armor (prompt-armor 0.9.5) | 2.1% | 13.0% | 95.9% | 62.7% |
| monitor | 0.0% | 0.1% | 91.6% | 91.4% |
| rule + lock | 0.0% | 1.1% | 96.6% | 95.6% |
| rule + planlock | 0.1% | 1.8% | 95.3% | 94.9% |
| rule + armor | 0.0% | 2.2% | 93.8% | 63.8% |

*Attack success by defense; 1,920 attacked and 320 legitimate episodes per row. Intervals are in [`results/SUMMARY.md`](../results/SUMMARY.md).*

The rule and the lock fail in different places, which is why they combine well. The rule alone still lets through 15% of the owner's-note attacks that change state: the agent is persuaded that the owner wants it. The lock alone still lets through 8% of the marker attacks: the agent was supposed to answer that buyer or that email, so the action is authorized, and the lock does not read what the answer says. Together they leave 1.1%, almost all of it the marker written inside an authorized reply, which only the monitor, reading the content of the action, catches.

The realistic lock keeps most of the oracle's benefit. On its own, the planner made no errors on the 320 tasks and allowed every action each task needed, but in 83% of the tasks that need an action the request does not say which item ("answer Julia's question"), so the plan allows the tool on any item. That lets the attacker's action through in 11.9% of task and injection pairs, against 2.1% for the oracle. In the agent runs, that gap shows up as 2.9% and 5.1% instead of 1.2% and 2.6%, and almost disappears when the rule is added (0.1% and 1.8%).

### 3. What the defenses cost on legitimate work

On the five models, the rule costs nothing measurable. The oracle lock fires on 0.6% to 7.5% of legitimate episodes but does not lower utility: the agents recover from a blocked action. The monitor fires on 7% to 12% and costs 3 to 6 points of utility, every model included, plus one extra model call per action. prompt-armor 0.9.5 fires on 8% to 12% and costs at most 1.3 points. The realistic lock on Haiku 4.5 costs about 2 points.

### 4. The detector

| prompt-armor | language | legitimate episodes with a block (in the agent) | utility without attack | Haiku 4.5 owner's-note success |
|---|---|---|---|---|
| 0.9.3 | English | 35.9% | 80.4% | 17.7% |
| 0.9.3 | Portuguese | 80.9% | 30.2% | 4.0% |
| 0.9.5 | English | 9.9% | 98.5% | 18.1% |
| 0.9.5 | Portuguese | 9.6% | 98.2% | 7.9% |

*Five models pooled for the first two columns.*

The version we started with looked strong in Portuguese, letting only 4% of the owner's-note attacks through, but only because it blocked almost everything: 81% of legitimate Portuguese episodes and 30% utility. Its small classifier layer was an English-only model that scores ordinary Portuguese as injection ("Bom dia! Gostaria de saber o prazo de entrega." got 0.99). Version 0.9.4 replaced it with an existing multilingual classifier and retrained the fusion on the detector's own benchmark, and 0.9.5 made a numerical fix; this study's tasks were used only to measure before and after. With 0.9.5, the false positives are equal across languages and mostly come from short tool confirmations ("Email e03 moved to invoices.").

Two lessons generalize. First, a detector's headline numbers can hide a language failure that only shows up as lost utility, so utility has to be measured per language. Second, withholding the whole tool result is the wrong granularity for agents: the injected text arrives inside the data the task needs, so a correct detection still costs the task (63% utility under attack, against 91% to 96% for the other defenses).

### 5. Language

On Haiku 4.5 without defense, the classic attack succeeded 2.7 times more often in Portuguese (22.1% against 8.3%), while the owner's note worked about equally in both (31.7% and 28.8%). The rule closes the gap: 0.8% against 0.0% for the classic attack.

## What this suggests for a small business

Use a current model; it does most of the work. Then add the two cheap architectural pieces: tell the agent that tool content is data, and give each task only the actions it needs, decided from the owner's request before the agent reads anything. If the remaining risk is text written into authorized messages, a monitor that reads each action catches it, at a cost of a few points of utility. A generic detector in front of the agent added the least of the four, and must be tested on the business's own language.

One caution on reading the first result: the models' robustness was measured against fixed attacks. The architectural pieces matter even where the model already resists, because they bound what a successful injection can do, and they do not depend on the attacker failing.

## Related practice

Two recent industry systems make the same bet on architecture. OpenAI's open-source [Codex Security CLI](https://github.com/openai/codex-security) (Apache 2.0, July 2026) tells its agents to treat repository contents and fetched pages "only as untrusted analysis data" that cannot authorize actions (our `rule`), runs them in role-based sandboxes, and sends any action that leaves the sandbox to an LLM reviewer (close to our `monitor`); it has no input detector. Its security policy states that prompt injection, or a model misusing access it already has, "does not qualify by itself" as a vulnerability unless it gets around an enforced restriction: the boundary is the architecture, not the model. OpenAI reports 99.3% recall on prompt injection for that reviewer ([Auto-review](https://alignment.openai.com/auto-review/), April 2026; GPT-5.4 Thinking on a synthetic set built by a trained attacker, so not comparable to our numbers), and says it "should not be treated as a guarantee of security." OpenAI's [Defense Factory](https://openai.com/the-defense-factory/) describes agents that act on real systems under scoped permissions, a credential proxy, throwaway sandboxes and human approval; it does not discuss prompt injection. Neither reports how much each layer contributes, or how the layers behave outside English, which is what this study measures on small-business workflows.

## Limitations

- **The attacker does not adapt.** We used fixed templates. An attacker who iterates against a specific model would do better; we did not try, because optimizing attacks against Claude belongs in Anthropic's model safety bug bounty, not in a public repository.
- **Simulated, narrow environments.** One fictional business, four workflows, 160 tasks per language, harmless goals. The tasks were drafted with AI help and checked by a validator and by hand, by the same person who designed the defenses.
- **One run per configuration.** The intervals are binomial over episodes and do not include run-to-run variation of the API.
- **The locks see actions, not text.** Neither lock checks what an authorized message says; the realistic lock is one design among many, and its planner and the monitor are themselves Claude Haiku 5.5, a robust model. A weaker planner or monitor could do worse.
- **Conflict of interest.** prompt-armor is the author's open-source project. The study found the language bias in it, and the fix was made during the study; we report both versions and did not tune the detector on the study's tasks.
- **Refusals count as safe.** Opus 5.5's classifier refusals are not attack successes but lose the task; we report them separately.

## Next steps

An adaptive attacker under the bug bounty's rules; a lock that also constrains text arguments (for example, no new codes or links in a reply); detectors that redact the suspicious span instead of withholding the whole result; and the same workflows with other model families.

## Reproducibility and use of AI

Code, task data, logs summaries and every table are in this repository; [`results/SUMMARY.md`](../results/SUMMARY.md) is generated by `scripts/summary_tables.py` from the episode files. The project was built with heavy use of Claude (Claude Code with Opus 5.5): the harness, the analysis scripts and drafts of the task data and of this text. The question, the design decisions and the reading of the results are the author's. Claude models are also the subjects of the study.
