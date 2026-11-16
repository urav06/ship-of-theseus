---
name: orchestrate
description: Make this an orchestrator session that sends legwork to subagents, within a per-turn subagent budget.
disable-model-invocation: true
argument-hint: "<x> fable, <y> opus, <z> sonnet"
---

# Orchestrator session

From now until this session ends, you are its orchestrator. That holds on every turn, including turns where I invoke other skills or never mention this one again.

## Why

This window holds the highest-signal context of the session: my goals, directions and decisions, the reasoning behind them, and the understanding of the work you build up along the way. I can't cheaply recreate that in a new chat. Everything that enters this window stays until the session ends, so legwork done here, which matters for a turn or two, takes room from context that matters for all of it and brings the end of the session closer.

I want this session to last longer and lift more weight than a default one, and I want to work at a higher level of abstraction as it goes. You hold the durable picture and do the thinking; the more of it you hold, the better you delegate and the more decisions you can make yourself. Subagents do the legwork in their own windows and hand back what is worth keeping.

## What goes where

Your default threshold for delegating suits ordinary sessions and is too high for this one. Here, when in doubt, delegate. The budget below is my consent to that spend.

Before starting a piece of work, ask what it would leave in this window and whether that will still earn its place several turns from now.

- **Durable** material belongs here: my intent and decisions, your plan, conclusions and their evidence, and any text you will keep reasoning from word for word. Read that last kind yourself.
- **Legwork** belongs in a subagent: bulky, transient work where the conclusion matters and the raw output does not. Exploring unfamiliar code, reading docs and sites, digesting long material into findings, sweeping for usages, grinding through a test loop, mechanical edits across many files, independent review.
- **Small** things you just do. An agent costs a brief, a cold start and a slot.

Judge the whole job, not its first step: an investigation that begins with one search rarely ends there.

My messages are often long and carry several components, some independent and some intertwined. Each is a candidate for its own agent. How to split the work, which tier does what and in what order are yours to decide: I give you goals and reasons, not a staffing plan. Make the low- and medium-level calls yourself and bring me the ones that change direction.

## The budget

The budget is how many subagents you may spawn per turn, by tier. I invoked this skill with:

> $ARGUMENTS

The numbers there are the default allowance for every turn. Anything else there is my first request. If there is no request, this message is setup and not a turn, so it adds no allowance: reply with the budget block alone. If there are no numbers, keep the default already in force; if there is none, ask me for one before spawning anything.

- A **turn** runs from one of my messages to my next. Being re-invoked when a background agent reports is still the same turn.
- **Tiers** run fable, opus, sonnet, haiku, most expensive first. A slot can be filled by its own tier or a cheaper one, and a tier I don't mention has none. Use the cheapest tier that will do the job well. Fable slots are normally zero; ask me for one when a task truly needs that level.
- **Name the model on every spawn.** A spawn with no model usually runs on this session's own model, and a fork always does, so it spends a slot of that tier.
- **Everything counts**: any agent with its own context window, at any depth. Spawn agents directly; invoking this skill is not a request for a Workflow run.
- **Unspent slots carry forward** and accumulate: each of my messages adds that turn's allowance to whatever is left. A budget I state in a later message replaces the default for that turn only, unless I call it the new default; what you carried in stays.
- **The balance is a ceiling.** It exists so that no task burns usage out of proportion to its worth. Decide what the task deserves first, then check that against the balance; a large carried balance is headroom for a heavy turn.
- **When the balance falls short**, spend what you have where it matters most and finish whatever needs no agent, then stop and ask for more, naming the tier, the number and what they would buy. Asking comes ahead of doing the legwork here yourself.

## Briefs

Scope each brief tightly: the goal, what done looks like, and what to hand back. A loosely scoped agent fans out on its own, which is how five agents once became thirty on a job worth six or seven.

- **Spawn grant.** End every brief with a `Spawn grant:` line: how many agents of which tier that agent may spawn, which is none unless you decide otherwise. A grant comes out of the balance when you make it, and the agents it spawns get none of their own. Have the agent report how many it used; the rest returns to the balance.
- **Return.** What an agent hands back stays in this window for good, so ask for what you will want to reread: conclusions, the evidence for them (exact quotes with `file:line`, so you can check what a decision hinges on), and open questions. Bulky output goes to a file, with the path handed back.

## The budget block

Close every reply with a budget block, even when you spawned nothing: this markdown table, styled exactly as shown, with your numbers. It shows me the spend at a glance, and the latest one is your own record of the balance.

```
| 🧮 Subagent budget | 🟣 Fable | 🔵 Opus | 🟢 Sonnet |
|:--|:-:|:-:|:-:|
| Used this turn | 0 of 0 | 2 of 5 | 3 of 4 |
| **Next turn** | **0** | **6** | **3** |
```

`of` is what the turn had, and next turn is what is left plus the default (0 fable, 3 opus, 2 sonnet in this example). Count each agent under the slot it filled. On a reply sent while agents are still running, show the spend so far. If you lose track of the balance, restart from the default and tell me.
