# OSHA AI - Test Questions

5 questions from easy → hard, covering CFR, OSH Act, and FOM.
Run each with: `python main.py`

---

## Q1 (Easy — CFR, single clear match)

**Question:** When must an employer report a workplace fatality to OSHA and how?

**Why easy:** Fatality reporting is uniquely in 1904.39 — no 1910 vs 1926 ambiguity, single clear match.
**Expected source:** `1904.39` — Reporting fatalities, hospitalizations, amputations, and losses of an eye
**What to look for in answer:**
- Fatality must be reported within 8 hours
- In-patient hospitalization, amputation, or loss of an eye within 24 hours
- Report by phone to nearest OSHA office, or online at osha.gov

---

## Q2 (Easy — OSH Act, definitional)

**Question:** What are the general duty obligations of an employer under the OSH Act?

**Why easy:** The OSH Act General Duty Clause is a standalone section, single match.
**Expected source:** `OSH-Act-Section-5` — Duties
**What to look for in answer:**
- Each employer shall furnish employment free from recognized hazards
- Each employee shall comply with standards applicable to their actions and conduct

---

## Q3 (Medium — CFR with ambiguity trigger)

**Question:** What are the fall protection requirements for workers?

**Why medium:** Triggers 1910 vs 1926 ambiguity — fall protection exists in both General Industry (1910) and Construction (1926). User must clarify industry type before locking.
**Note:** Eye/face protection ("1910.133 vs 1926.102") also triggers this same flow — both parts have duplicate coverage on PPE topics.
**Expected behavior:**
- System returns `ambiguous: true`
- Prompt asks: General Industry (1910) or Construction (1926)?
- After clarifying Construction → lock `1926.502` for full answer
**What to look for after clarifying 1926:**
- Guardrail systems, safety net systems, personal fall arrest systems
- 6-foot threshold for construction work

---

## Q4 (Medium — FOM procedural, multi-step)

**Question:** How does an OSHA compliance officer conduct an opening conference during an inspection?

**Why medium:** FOM procedural knowledge, not in CFR. Requires knowing to look in FOM chapters, not regulations.
**Expected source:** `FOM-Chapter-3` — Inspection Procedures
**What to look for in answer:**
- Compliance officer identifies themselves and explains purpose of the inspection
- Employer may have a representative accompany the CSHO
- Scope and nature of the inspection explained
- Right to refuse entry (without a warrant) noted

---

## Q5 (Hard — cross-document, multi-section lock)

**Question:** A worker died on a construction site today. What are the employer's legal reporting obligations, what authority does OSHA have to inspect, and what violations could result?

**Why hard:** Spans three source types — employer must:
1. Report to OSHA (CFR 1904.39 — within 8 hours)
2. OSHA has inspection authority (OSH Act Section 8)
3. Fatality investigation process (FOM Chapter 11)
4. Potential willful/serious violations (FOM Chapter 4 or 6)

**Expected behavior:**
- Multiple top results from different parts (1904, FOM, OSH Act)
- No ambiguity flag (different regulatory parts, not competing scopes)
- Lock: `1904.39` + `FOM-Chapter-11` + `OSH-Act-Section-8`
**What to look for in combined answer:**
- Fatality reported within 8 hours by phone or online
- OSHA authority to enter without delay, inspect records, question employees
- Fatality triggers mandatory OSHA investigation
- Potential criminal referral if willful violation caused death
