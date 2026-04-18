# Improved System Prompt — Camp-Nou AI Scheduler Rewrite

---

## CONTEXT

You are rewriting the LangGraph/LangChain scheduling system for the **Camp-Nou** college timetable orchestration project.

**Current state:** The existing graph nodes (`scheduler.py` and `timetable_scheduler.py`) use only deterministic Python sorting algorithms — no AI is involved. Your job is to replace the logic inside the LangGraph nodes with actual calls to a locally-hosted **Gemma 4** model so that Gemma makes the scheduling decisions, not hard-coded algorithms.

**What already exists and must NOT be changed:**
- The FastAPI backend structure (`server/services/`, `server/main.py`)
- The SQLAlchemy models: `Students`, `Rooms`, `Classrooms`, `Subjects`, `Faculty`, `SubjectFacultyMapping`, `Timetable`
- The Excel upload scripts in `server/scripts/` (rooms.py, students.py, subjects_faculty.py)
- The React frontend in `client/src/App.jsx` — it calls these endpoints and expects the same JSON shapes:
  - `POST /api/v1/timetable/generate` → `{ message, warnings[], classes_scheduled[] }`
  - `GET /api/v1/timetable/all` → `{ class_name: { day: [{ slot, subject_id, faculty_id, room_id, is_lab_period, status }] } }`
  - `GET /api/v1/timetable/{class_name}` → `{ class_name, timetable: { day: { "1..6": { subject_id, faculty_id, room_id, is_lab_period, status } } } }`
- The database schema — do not add or remove columns

**Files you ARE rewriting:**
- `server/services/graph/scheduler.py` — student sorting + room allocation graph
- `server/services/graph/timetable_scheduler.py` — full timetable scheduling graph

---

## AI MODEL CONFIGURATION

- **Model:** Gemma 4 (gemma-4 or the currently loaded model slug in LM Studio)
- **Endpoint:** `http://127.0.0.1:1234/v1` (OpenAI-compatible, served by LM Studio)
- **Integration:** Use `langchain_openai.ChatOpenAI` pointed at the LM Studio base URL, **not** the OpenAI API
- **Temperature:** Use a low value (0.1–0.3) for deterministic, reproducible scheduling decisions
- **Output format:** Always instruct Gemma to respond in **valid JSON only** (no markdown fences, no prose before/after). Use `response_format={"type": "json_object"}` if the LM Studio build supports it; otherwise enforce JSON via the system prompt and parse with a fallback
- **Fallback:** If Gemma returns malformed JSON or violates a hard constraint (double-booking, missing field), the graph node must fall back to the deterministic Python algorithm for that specific decision only, log a warning, and continue — never crash the full workflow

**LangChain wiring example (do not deviate from this pattern):**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gemma-4",           # match the model name shown in LM Studio
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio",       # LM Studio ignores this but LangChain requires it
    temperature=0.2,
)
```

---

## GRAPH ARCHITECTURE

Keep the existing LangGraph `StateGraph` wiring. Replace the logic **inside** each node function. Do not rename nodes, do not remove edges.

### Graph 1 — `scheduler.py` (Student Sorter + Room Allocator)

**Node: `fetch_data`** — unchanged (DB fetch only)

**Node: `sort_students` — AI-powered**

Ask Gemma to group students into branch-based sections given:
- The full list of students: `[{id, name, branch}]`
- Room capacity constraints: `[{id, name, capacity}]`
- Target: produce named sections (e.g. `CS-A`, `CS-B`, `EC-A`) such that each section fits within one room's capacity

Prompt Gemma with a JSON payload and ask for a JSON response with this shape:
```json
{
  "sections": [
    {
      "section_name": "CS-A",
      "branch": "CS",
      "student_ids": [1, 2, 3, ...]
    }
  ]
}
```

Validation after Gemma responds:
- Every student must appear in exactly one section (no orphans, no duplicates)
- Each section's student count must not exceed the assigned room's capacity
- If validation fails, fall back to the existing sorted-by-id deterministic logic

**Node: `allocate_room` — AI-powered**

Ask Gemma to assign one room to each section given:
- Sections from the previous step
- Available rooms with capacities and `room_type` (`classroom` / `lab`)
- Only `room_type = "classroom"` rooms may be assigned as homerooms to sections

Gemma returns:
```json
{
  "allocations": [
    { "section_name": "CS-A", "room_id": 1, "room_name": "CR-101" }
  ]
}
```

Validation:
- No room may appear twice in the allocations list
- Assigned room capacity ≥ section student count

**Node: `save_assignments`** — unchanged (DB write only)

---

### Graph 2 — `timetable_scheduler.py` (Full Timetable Generator)

**Node: `fetch_all_data`** — unchanged

**Node: `build_constraints`** — unchanged (pure data transformation)

**Node: `generate_initial_timetable` — AI-powered**

This is the core scheduling node. Replace the greedy slot-fill algorithm.

Pass Gemma the full constraint set as a structured JSON prompt:

```json
{
  "task": "generate_college_timetable",
  "constraints": {
    "days": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"],
    "slots_per_day": 6,
    "lab_duration_slots": 3,
    "classes": ["CS-A","CS-B","CS-C","EC-A","EC-B"],
    "classrooms": [{"id":1,"name":"CR-101","capacity":60}, ...],
    "labs": [{"id":4,"name":"LAB-201","capacity":30}, ...],
    "subjects": [{"id":1,"name":"Mathematics","is_lab":false,"hours_per_week":4}, ...],
    "faculty_mappings": [
      {"class_name":"CS-A","subject_id":1,"faculty_id":2,"is_lab":false,"hours":4},
      ...
    ]
  },
  "hard_constraints": [
    "A faculty member may teach at most one class in any given (day, slot)",
    "A room may be occupied by at most one class in any given (day, slot)",
    "Lab sessions must occupy exactly 3 consecutive slots on the same day",
    "Lab sessions must be assigned to a room with room_type=lab",
    "Lecture sessions must be assigned to a room with room_type=classroom",
    "Every subject's required hours_per_week must be scheduled across the week"
  ],
  "soft_constraints": [
    "Distribute a subject's hours evenly across different days where possible",
    "Avoid scheduling more than 2 consecutive lectures of the same subject for one class",
    "Prefer scheduling lab sessions earlier in the week"
  ],
  "room_scarcity_rules": [
    "If the number of classes exceeds the number of classrooms, stagger classes so their lecture slots do not overlap where possible",
    "When a class leaves its classroom for a lab session, that classroom slot becomes free and may be reused by another class",
    "An unused lab room (no lab session at that slot) may be reassigned as a classroom for that slot only",
    "If a slot cannot be assigned any room, mark it status=unassigned_room and record it in the conflicts list for the resolve step"
  ]
}
```

Gemma must return the full timetable in this exact shape (matching the existing `TimetableState.timetable` structure):
```json
{
  "timetable": {
    "CS-A": {
      "Monday": {
        "1": {"subject_id":1,"faculty_id":2,"room_id":1,"is_lab_period":false,"status":"scheduled"},
        "2": {"subject_id":3,"faculty_id":5,"room_id":1,"is_lab_period":false,"status":"scheduled"}
      }
    }
  },
  "conflicts": [
    {"class_name":"CS-B","day":"Tuesday","slot":3,"subject_id":2,"faculty_id":3,"reason":"no_classroom_available"}
  ],
  "warnings": []
}
```

**Important:** After Gemma returns, run the existing Python constraint-checker functions (`_is_room_free`, `_is_faculty_free`, `_is_room_free` etc.) to validate the output slot-by-slot before accepting it. If Gemma violates hard constraints, log which entries are invalid, remove them from the timetable, add them to `conflicts`, and let `resolve_room_conflicts` handle them.

**Node: `resolve_room_conflicts` — AI-assisted**

Pass the current `conflicts` list plus the current `timetable` and `room_schedule` snapshots to Gemma and ask it to propose a resolution for each conflict. Gemma should choose one of:
1. `lab_displacement` — another class is in lab at this slot, so use the classroom it vacated
2. `reschedule` — move the period to a different (day, slot) pair that has a free room and free faculty
3. `use_lab_as_classroom` — if the lab room is free at this slot (no lab session), use it as a fallback classroom
4. `suspend` — no option works; mark status=suspended

Gemma returns:
```json
{
  "resolutions": [
    {
      "class_name": "CS-B",
      "original_day": "Tuesday",
      "original_slot": 3,
      "action": "reschedule",
      "new_day": "Wednesday",
      "new_slot": 2,
      "room_id": 2
    }
  ]
}
```

After applying Gemma's resolutions, run the Python constraint checker again. Any entry that still violates hard constraints falls back to Python strategy 3 (suspend).

**Node: `validate_timetable`** — unchanged (deterministic double-booking check)

**Node: `save_timetable`** — unchanged (DB write only)

---

## HARD EDGE CASES GEMMA MUST HANDLE

> Include these explicitly in every scheduling prompt so Gemma is aware:

1. **Room scarcity (more classes than classrooms):** Stagger overlapping slots. Exploit lab-period vacancies.
2. **Faculty teaching multiple classes:** The same `faculty_id` can appear in many `faculty_mappings` rows for different classes. Gemma must track faculty across all classes simultaneously.
3. **Lab rooms as temporary classrooms:** A lab room with `room_type=lab` is only available as a fallback classroom during slots where no class has a lab assignment. Never assign a lab room as a classroom if any class has a lab period in that same slot.
4. **Consecutive lab slots:** Labs must be 3 back-to-back slots. Gemma must not split them across days or leave gaps.
5. **Hours balance:** Every subject's `hours_per_week` must be fully scheduled. If it cannot be, emit a warning — do not silently drop hours.
6. **Empty data:** If `classrooms`, `labs`, or `faculty_mappings` is empty, the node must return an empty timetable with an explanatory warning rather than crashing.
7. **Gemma timeout/malformed JSON:** Wrap every LLM call in a `try/except`. On failure, fall back to the deterministic algorithm for that node only and append `"AI fallback used"` to `warnings`.
8. **Duplicate section names across branches:** Student sections from different branches may share the same letter (e.g. `CS-A` and `EC-A`). Ensure section names always include the branch prefix.

---

## INPUT / OUTPUT CONTRACT (do not break these)

### Input to the graph (from uploaded Excel sheets, parsed by existing scripts)

The three Excel files produce DB rows that the graph reads at `fetch_all_data` / `fetch_data`:

| Table | Key columns |
|-------|-------------|
| `rooms` | id, name, capacity, room_type (`classroom`/`lab`) |
| `students` | id, name, branch |
| `subjects` | id, name, is_lab, hours_per_week |
| `faculty` | id, name |
| `subject_faculty_mapping` | subject_id, faculty_id, class_name |

### Output from the graph (consumed by the React frontend)

The `Timetable` table rows must have:
- `class_name` — string like `"CS-A"`
- `day` — one of `["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]`
- `slot` — integer 1–6
- `subject_id`, `faculty_id`, `room_id` — integer foreign keys (nullable only for `status=suspended`)
- `is_lab_period` — boolean
- `status` — one of `"scheduled"`, `"rescheduled"`, `"unassigned_room"`, `"suspended"`

The `GET /api/v1/timetable/{class_name}` endpoint shape (used by the timetable grid in the UI) must remain:
```json
{
  "class_name": "CS-A",
  "timetable": {
    "Monday": { "1": {…}, "2": {…}, … "6": {…} },
    …
  }
}
```

---

## WHAT NOT TO CHANGE

- Do not rename or remove any LangGraph node names or graph edges
- Do not alter FastAPI route paths, HTTP methods, or response schemas
- Do not change SQLAlchemy model column names or types
- Do not modify the Excel upload scripts (`server/scripts/`)
- Do not touch the React frontend
- Do not use `openai` Python SDK directly — use `langchain_openai.ChatOpenAI`
- Do not add external databases, message queues, or new Python dependencies beyond `langchain-openai` and `langchain-core`

---

## CHANGES MADE TO THE ORIGINAL PROMPT

| # | Original | Improved |
|---|----------|----------|
| 1 | Said "rewrite every langgraph/langchain stuff" without specifying which files | Explicitly names `scheduler.py` and `timetable_scheduler.py` as the only targets |
| 2 | No mention of which nodes should be AI vs. deterministic | Specifies node-by-node: data-fetch and DB-save nodes stay deterministic; decision nodes use AI |
| 3 | "utilize gemma 4 ai hosted on lm studio at http://127.0.0.1:1234" — no integration detail | Added exact `langchain_openai.ChatOpenAI` wiring with `base_url`, `api_key`, and `temperature` |
| 4 | No JSON schema for what Gemma should return | Added explicit expected JSON response shapes for every AI-powered node |
| 5 | No mention of fallback behavior | Added requirement: fallback to deterministic algorithm per-node on AI failure; append warning |
| 6 | "no overlap of classes and one faculty can only be present in one class at a time" | Reformulated as explicit hard constraints in the prompt payload so Gemma receives them in context |
| 7 | Lab room dual-use rule mentioned loosely | Clarified: lab rooms usable as classrooms only when no other class has a lab session in that slot |
| 8 | No validation step after Gemma output | Added post-AI Python constraint-checker pass; violations get demoted to conflicts for the resolve node |
| 9 | "input json structure should follow new .xlsx files" — vague | Provided exact table-to-column mapping matching the existing SQLAlchemy models |
| 10 | "output should work with the frontend in the client directory" — vague | Listed the exact API endpoint response shapes the frontend expects with field-level detail |
| 11 | No mention of the `status` field values | Enumerated valid status values (`scheduled`, `rescheduled`, `unassigned_room`, `suspended`) |
| 12 | No mention of Gemma timeout / malformed JSON | Added try/except requirement and fallback logging strategy |
| 13 | No guidance on temperature or JSON-mode | Recommended temperature 0.1–0.3 and `response_format={"type":"json_object"}` where supported |
| 14 | Edge cases mentioned in prose without structure | Listed all 8 critical edge cases as numbered items to be included in every scheduling prompt |
| 15 | No "do not change" boundary | Added explicit list of files/schemas/routes that must remain untouched |
