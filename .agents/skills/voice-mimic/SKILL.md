---
name: voice-mimic
description: Analyzes writing samples to extract an authentic Voice DNA profile (cadence, sentence burstiness, vocabulary, tone, negative space) and generates or revises drafts to match that exact personal voice with zero AI cliches.
---

# Voice Mimic & Writing Style Extraction Skill

Inspired by the top open-source stylometry and author-mimic frameworks (`write-like-me`, Fabric's `analyze_prose`, and `opinion-os`), this skill enables the agent to systematically reverse-engineer how a user writes and produce new content (blog posts, READMEs, emails, docs) that faithfully mirrors their authentic voice.

---

## 1. The Two Operational Modes

### Mode 1: Analyze Writing Style (`/voice-mimic analyze`)
When given one or more raw writing samples from the user:
1. **Corpus Scrubbing**: Strip away third-party quotes, automated headers, and AI-generated echoes.
2. **6-Dimensional Stylometric Analysis**:
   - **Cadence & Sentence Architecture**: Mean sentence length, burstiness (standard deviation), short sentence ratio (≤6 words), long compound ratio (≥28 words), sentence openers.
   - **Vocabulary & Diction**: Latinate/abstract vs. Anglo-Saxon/concrete nouns, contraction density (>80% vs <20%), technical shorthand, epistemic calibration (hedging tokens like *perhaps/seems* vs boosting tokens like *clearly/never*).
   - **Tone & Persona**: Register (conversational, pragmatic, analytical, informal), emotional distance, humor style (deadpan, self-deprecating, sarcastic, earnest).
   - **Punctuation & Mechanics**: Density of em dashes (`—`), semicolons, colons, parentheses for conversational asides, ellipses, exclamation marks, and list formats.
   - **Rhetorical Movements**: Hook patterns (problem-first, personal dread, BLUF), transition habits, and conclusion shapes (action item, callback, open thought).
   - **Negative Space (What the Author NEVER Does)**: Structural shapes, tropes, or words conspicuously absent from the corpus.
3. **Select 2–3 Annotated Exemplars**: Choose gold-standard paragraphs from the user's text and annotate *why* they define the voice.
4. **Synthesize `VOICE_DNA.md`**: Generate and save the structured profile in the workspace.

### Mode 2: Write & Revise in Voice (`/voice-mimic write` or `/voice-mimic revise`)
When drafting or editing prose:
1. **Load Target Profile**: Read the active `VOICE_DNA.md` profile.
2. **Drafting Phase**: Emulate the author's sentence length targets, clause linkages, diction register, and rhetorical moves.
3. **Pre-Delivery Verification Gate**: Before outputting the text, run the internal verification scan (or execute `python scripts/voice_check.py <draft.md>`). If any AI tell or negative-space violation is detected, automatically rewrite the offending line before presenting it.

---

## 2. Universal Anti-AI Baseline (Always Active)

Regardless of the target voice, the following AI writing tics are strictly prohibited:
- **No Em Dashes (`—`) as Default Clause Separators**: Use commas, periods, or parentheses instead.
- **No Stance Adverbials as Openers**: Ban `Honestly`, `Frankly`, `Crucially`, `Importantly`, `Interestingly`, `Notably`, `Obviously`, `Clearly`.
- **No Filler Openings**: Ban `It is worth noting that`, `In today's fast-paced world`, `Needless to say`, `It goes without saying`.
- **No Empty Evaluative Hype**: Ban `game-changing`, `groundbreaking`, `revolutionary`, `robust`, `vital`, `cutting-edge`, `seamless`.
- **No Performative AI Verbs**: Ban `delve`, `leverage`, `foster`, `utilize`, `underscore`, `illuminate`, `elucidate`.
- **No Rhetorical Amplifiers**: Ban the `not only X, but also Y` construction.
- **No Formal Summary Openers**: Ban `In conclusion`, `To summarize`, `In summary`, `To recap`.

---

## 3. The "Anti-Tic Abstraction Principle"

Do NOT instruct the model using fixed lists of catchphrases or repetitive idioms. If given a static list of words, an LLM will compulsively repeat them every three paragraphs, degrading the writing into a parody.

Instead, describe **syntactic tendencies, cognitive posture, and rhythmic variance**:
- *Wrong:* "Always say 'to be honest' and 'down the rabbit hole'."
- *Right:* "Favors concrete mechanical analogies over abstract nouns. Mixes rapid 4-word observations with extended, comma-linked causal chains. Skeptical of unmeasured claims."

---

## 4. `VOICE_DNA.md` Target Schema

When saving a voice profile, use this standard schema:

```markdown
# Voice DNA: [Name / Register]

## 1. Core Persona & Mechanics
[2-3 sentences summarizing the author's primary communication stance]

## 2. Quantitative Targets & Cadence
- **Target Mean Sentence Length**: [e.g., 14 - 18 words]
- **Burstiness**: [High / Moderate / Low sentence length variance]
- **Staccato Sentence Ratio (<=6 words)**: [e.g., ~15%]
- **Extended Sentence Ratio (>=28 words)**: [e.g., ~10%]
- **Contraction Frequency**: [e.g., High (>85%)]
- **Epistemic Stance**: [Calibrated uncertainty vs Assertive authority]

## 3. Diction, Tone & Register
- **Register**: [e.g., Pragmatic engineer, conversational analytical]
- **Vocabulary Style**: [Sensory, literal, concrete tools and numbers]
- **Humor & Subtext**: [Deadpan, dry, self-deprecating]

## 4. Punctuation & Formatting Conventions
- **Punctuation Rules**: [Density of dashes, semicolons, parens]
- **Formatting**: [Short paragraphs, bulleted lists, bolding]

## 5. Negative Space (Hard Restrictions)
- **Forbidden Phrases**: [Specific tropes the author never uses]
- **Banned Structures**: [e.g., Never uses rhetorical questions or announcement colons]

## 6. Annotated Gold-Standard Exemplars
> [Exemplar 1 text]
*Why it works: [Structural notes on rhythm, transition, and tone]*

> [Exemplar 2 text]
*Why it works: [Structural notes]*
```

---

## 5. Pre-Delivery Verification Checklist

Before delivering any draft written in voice, check off:
- [ ] Are all sentence openers diverse (no consecutive sentences starting with the same word)?
- [ ] Is mean sentence length within the target range?
- [ ] Are there at least two short staccato sentences (≤6 words) per section?
- [ ] Zero instances of `delve`, `leverage`, `seamless`, `robust`, `testament`, or `crucial`?
- [ ] Zero em dashes used as lazy thought connectors?
- [ ] Does the hook immediately state a real human friction without throat-clearing?
- [ ] Are negative-space constraints 100% respected?
