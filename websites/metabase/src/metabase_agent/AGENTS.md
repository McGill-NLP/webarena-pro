# Metabase Browser Agent — Implementation Plan

## Goal

Build a Python-based browser agent that can complete tasks inside a local Metabase instance using browser automation.

The agent should:
- run against a local Docker Metabase environment
- use Playwright for browser control
- use AgentLab’s `GenericAgent` as the decision-making layer
- support headless mode by default
- support demo/headed mode for debugging
- start with a small set of simple tasks and expand gradually

---

## Core idea

This is not a traditional chatbot product.

The system should work like this:

1. A task is defined in a structured format.
2. A Python runner starts a browser session.
3. The browser sees Metabase and produces an observation.
4. `GenericAgent` reads the observation and decides the next action.
5. Playwright executes the action.
6. Repeat until the task is complete or the max step limit is reached.

So the agent is closer to an autonomous browser operator than a chat UI.

---

## Important decision

Do not modify Metabase source code at first.

Instead:
- run a local Metabase container with Docker
- seed it with test data, dashboards, and users
- let the agent operate Metabase like a real user would

This keeps the project safe, reproducible, and easy to debug.

---

## MVP scope

Start with a minimal set of tasks:

1. Log into Metabase
2. Open a dashboard or question
3. Apply a filter
4. Save the result
5. Export data or download a PDF

Do not start with:
- permissions management
- advanced subscriptions
- complex SQL generation
- cleanup/migration tasks

Those can come later.

---

## Suggested architecture

Use a small Python codebase with clear separation of responsibilities.

### High-level components

- **Metabase environment**
  - local Docker Metabase
  - sample data database
  - test users and dashboards

- **Task runner**
  - loads a task
  - starts a browser session
  - loops until success/failure

- **Browser environment**
  - Playwright-based
  - returns observations and executes actions

- **Agent adapter**
  - wraps AgentLab `GenericAgent`
  - converts observations into actions
  - keeps the rest of the app independent from AgentLab internals

- **Evaluator**
  - checks whether the task was completed successfully

- **Artifact logging**
  - screenshots
  - action traces
  - prompts/responses
  - saved files
  - run metadata

---

## Recommended repo structure

Use a clean structure like this:

```text
metabase-agent/
  agent.md
  docker-compose.yml
  .env.example
  README.md
  pyproject.toml

  src/
    metabase_agent/
      __init__.py

      cli.py
      config.py
      runner.py

      agent/
        __init__.py
        generic_agent_adapter.py
        models.py

      env/
        __init__.py
        base.py
        playwright_env.py

      tasks/
        __init__.py
        models.py
        loader.py
        examples/
          filter_and_save_question.yaml
          export_dashboard.yaml

      evaluation/
        __init__.py
        base.py
        rules.py

      metabase/
        __init__.py
        auth.py
        seed.py
        api.py

      logging/
        __init__.py
        artifacts.py
        traces.py
```

You can simplify this further at the start if needed, but keep the separation between:
- tasks
- environment
- agent
- evaluation

---

## Key abstractions to implement

### 1. `TaskSpec`

Represents one browser task.

Suggested fields:
- `id`
- `name`
- `instruction`
- `start_url`
- `timeout_seconds`
- `max_steps`
- `success_criteria`
- `tags`
- `notes`

Example idea:

```python
@dataclass
class TaskSpec:
    id: str
    name: str
    instruction: str
    start_url: str
    max_steps: int = 30
    timeout_seconds: int = 600
    success_criteria: list[str] = field(default_factory=list)
```

---

### 2. `Observation`

Represents what the browser/agent sees.

This may include:
- screenshot path or image bytes
- current URL
- DOM / accessibility tree / HTML snapshot
- open tabs
- metadata about the current page

If BrowserGym already provides a structured observation, reuse that instead of inventing a new format.

---

### 3. `AgentAction`

Represents what the agent wants to do next.

Examples:
- click an element
- type into an input
- select from a dropdown
- navigate to a URL
- press keyboard shortcut
- scroll

If AgentLab already defines the action format, use that format directly.

---

### 4. `BrowserEnv`

This is the browser control interface.

It should expose something like:

```python
class BrowserEnv(Protocol):
    def reset(self, task: TaskSpec) -> Observation: ...
    def step(self, action: Any) -> tuple[Observation, float, bool, dict]: ...
    def close(self) -> None: ...
```

This makes the rest of the app independent from the exact browser implementation.

---

### 5. `AgentController`

This wraps AgentLab `GenericAgent`.

It should:
- accept observations
- call `GenericAgent.get_action(obs)`
- return the resulting action and metadata

Keep AgentLab-specific code isolated here.

---

### 6. `TaskRunner`

This is the main orchestration loop.

It should:
- load the task
- create the environment
- reset the agent
- run the step loop
- stop on success/failure/timeout
- save artifacts

---

### 7. `Evaluator`

This checks whether the task succeeded.

Use simple evaluators first:
- page contains expected text
- URL matches expected route
- dashboard/question exists
- file download exists
- title changed as expected

Later, add stronger checks using:
- Metabase APIs
- database queries
- object metadata inspection

---

## Implementation order

Build in this exact order.

### Phase 1: project scaffold
Create:
- Python project structure
- configuration loading
- logging setup
- task model
- task loader
- empty runner CLI

Acceptance criteria:
- `python -m metabase_agent.cli` starts cleanly
- task YAML/JSON can be loaded successfully

---

### Phase 2: local Metabase environment
Create Docker setup for:
- Metabase
- database backend
- sample data source

Acceptance criteria:
- Metabase runs locally
- you can log in manually
- there is at least one dashboard and one question to work with

---

### Phase 3: browser environment
Implement a Playwright-based environment wrapper.

Acceptance criteria:
- browser launches in headless mode
- browser can open Metabase
- login flow works
- screenshots and page state can be captured

---

### Phase 4: generic agent integration
Wrap AgentLab `GenericAgent`.

Acceptance criteria:
- agent receives observations
- agent returns a valid browser action
- actions are executed in the browser
- the loop repeats for multiple steps

---

### Phase 5: first end-to-end task
Implement a single simple task:
- open dashboard
- apply filter
- save or export result

Acceptance criteria:
- the agent completes the task without manual intervention
- run output includes traces and screenshots
- success is detectable programmatically

---

### Phase 6: evaluation and artifact logging
Add:
- per-step screenshots
- action traces
- prompt/response logs
- final task result summary
- run folder per execution

Acceptance criteria:
- every run produces a traceable artifact folder
- failures are debuggable

---

### Phase 7: expand task library
Add more tasks one by one:
- bookmark/share dashboard
- export CSV/PDF
- create dashboard
- create/update question
- SQL question with join
- subscriptions
- permissions
- cleanup tasks

---

## Task file format

Use YAML for easy editing.

Example:

```yaml
id: filter_and_save_question
name: Filter and save a question
instruction: >
  Open the Sales dashboard, filter region to Canada, and save the result
  as a new question named "Sales - Canada".
start_url: http://localhost:3000
max_steps: 25
timeout_seconds: 600
success_criteria:
  - saved_question_exists
  - title_contains: Canada
tags:
  - beginner
  - dashboard
```

---

## Suggested folder responsibilities

### `config.py`
- read environment variables
- build app config object
- expose Metabase URL, credentials, headless flag, model config

### `cli.py`
- parse command-line args
- run a task by ID or path
- set demo/headless mode
- choose the model config

### `runner.py`
- owns the main loop
- coordinates env, agent, and evaluator
- stores artifacts
- handles timeouts and exceptions

### `env/playwright_env.py`
- launch browser
- open pages
- apply actions
- gather observations
- return step results

### `agent/generic_agent_adapter.py`
- instantiate `GenericAgent`
- pass observations into `get_action`
- expose a clean interface for the runner

### `tasks/loader.py`
- load YAML/JSON task files
- validate schema
- return `TaskSpec`

### `evaluation/rules.py`
- implement simple success checks
- eventually support task-specific validators

### `metabase/seed.py`
- create or refresh test data
- create sample dashboards/questions/users
- help reset the environment between runs

### `logging/artifacts.py`
- create run directories
- save screenshots and traces
- write summary JSON

---

## Logging and debugging requirements

The first version should save all of these:

- task definition used
- current step number
- action taken
- observation summary
- screenshot
- page URL
- final result
- error messages if the run fails

This is crucial because browser agents are hard to debug without traces.

---

## Non-goals for the first version

Do not build these yet:
- a frontend chatbot UI
- multi-agent orchestration
- production deployment
- direct Metabase source code patches
- complex natural language planning UI
- fully generic benchmark infrastructure

Keep the first version small and reliable.

---

## Local development assumptions

The project should assume:

- Python 3.11+
- Docker and Docker Compose installed
- local Metabase at `http://localhost:3000`
- a seeded test account exists
- model credentials are provided through environment variables
- headless browser mode is the default

Use `.env.example` to document required environment variables.

Example variables:

```bash
METABASE_URL=http://localhost:3000
METABASE_USERNAME=agent@example.com
METABASE_PASSWORD=changeme
HEADLESS=true
MODEL_NAME=...
MODEL_API_KEY=...
MODEL_BASE_URL=...
```

---

## Important design principle

Keep AgentLab behind a thin adapter.

Do not let the entire codebase depend directly on `GenericAgent` internals.

Instead:
- `runner` talks to `AgentController`
- `AgentController` talks to AgentLab
- `runner` talks to `BrowserEnv`
- `BrowserEnv` talks to Playwright

This will make the code easier to swap, debug, and extend.

---

## Suggested first milestone

A good first milestone is:

- start local Metabase in Docker
- log in as a test user
- open a dashboard
- apply one filter
- save the result
- verify the saved object exists

If that works, the architecture is good enough to expand.

---

## Acceptance criteria for MVP

The MVP is done when:

- Metabase runs locally in Docker
- the agent can log in and navigate
- the agent can complete at least one simple task end-to-end
- the run is reproducible
- artifacts are saved
- success is automatically checked

---

## Instructions for Cursor

When implementing this project:

1. Start with the repo scaffold.
2. Add config/task models first.
3. Build the browser wrapper next.
4. Add the AgentLab adapter after that.
5. Implement the runner loop.
6. Add one simple task and one evaluator.
7. Only then expand to more complex Metabase actions.

Prefer:
- small modules
- type hints
- dataclasses
- clear naming
- simple control flow
- explicit logs

Avoid:
- over-engineering early
- too many abstractions
- direct source modifications to Metabase
- building a UI before the agent loop works

---

If you want, I can next turn this into a **more concrete starter repo skeleton** with:
- actual file contents
- starter Python classes
- `docker-compose.yml`
- a first `filter_and_save_question.yaml` task
- a minimal `runner.py` Cursor can start filling in