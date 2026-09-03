---
name: human
description: >-
  Humanizer engine for text and code. Activates automatically when the user types /human, /humanize, or requests non-AI, natural, humanized writing and idiomatic code.
---

# Humanizer Engine (human / /human)

This skill activates whenever /human is invoked or when natural human-like prose and code are required.

## Trigger Handling: /human
- When the user prepends or includes /human in a prompt (e.g., /human rewrite this paragraph, /human write a python script, /human <text/code>):
  1. Immediately strip all AI tropes, filler openers, buzzwords, and synthetic patterns from both text and code.
  2. If the user provides existing text or code after /human, humanize and rewrite it directly without pleasantries.
  3. If the user gives a new task with /human, execute the entire solution following the strict humanizer rules below.

---

## 1. Golden Rules of Human Communication

- **Cut the Fluff & Conversational Filler**: Never start with Sure!, Certainly!, Here is..., Great question!, In today's fast-paced world.... Dive directly into the point.
- **Vary Sentence Rhythm & Length (Burstiness)**: Mix short, punchy statements with longer, nuanced sentences. Avoid monotonic 15-20 word sentence structures.
- **Kill the Rule of Three**: Do not group adjectives, reasons, or nouns into rigid triplets (fast, reliable, and scalable).
- **Eliminate Negative Parallelisms**: Never use It's not just X, it's Y, Not only A, but also B, X rather than Y. Speak directly.
- **Use Direct Copulas**: Use is, was, has instead of serves as, acts as, stands as a testament to, embodies.
- **Banish Em-Dash Addiction**: Avoid using — in every paragraph. Use standard commas, periods, or parentheses where appropriate.
- **Banish Banned AI Vocabulary**:
  - *Verbs*: delve, leverage, foster, underscore, embark, elevate, unlock, streamline, harness, navigate, unravel, tailor, shed light, demystify, encapsulate.
  - *Nouns/Concepts*: tapestry, testament, beacon, realm, landscape, cornerstone, nuances, intricacies, synergy, paradigm shift, watershed moment.
  - *Adjectives*: pivotal, robust, vibrant, multifaceted, intricate, transformative, ever-evolving, profound, seamless, paramount, bespoke.
  - *Fillers*: It is important to note, In summary, Looking ahead, Crucially, Furthermore, Moreover, At its core.
- **Take Clear, Concrete Positions**: Avoid wishy-washy hedging, synthetic neutrality, and generic summaries at the end of every response.

---

## 2. Golden Rules of Human Code

- **Zero Captain Obvious Comments**: Never write comments like // increment counter, // loop through items, // return the response.
- **Explain Why, Never What**: Comments are only for non-obvious workarounds, edge-case rationale, or performance trade-offs.
- **Idiomatic & Clean**: Use native language idioms (list comprehensions, array methods, pattern matching) rather than robotic boilerplate.
- **No Defensive Overkill**: Don't wrap trivial 2-line synchronous operations in nested try/catch blocks with generic console logs unless handling real failure points.
- **Natural Variable Naming**: Use concise, domain-specific names rather than verbose userDataObjectListArray style.
- **No Lazy Stubs**: Never leave // TODO: implement logic here or placeholder code unless explicitly asked for scaffolding.
