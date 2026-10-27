# Source, model and execution boundaries

Scope: the user's owned NOVA candidate branch, synthetic fixtures and the fixed
local model service. Authority: the supplied request to implement the NOVA
work layer and integrate the existing local source modules. This authorizes
local development and bounded tests, not third-party probing or device control.

## Separate capabilities

1. Source ingestion preserves bytes as data. Static adapters produce derived
   text, AST, pixels, media frames or inferred speech. They never import or run
   ingested code. Source status and parent status remain relevant downstream.
2. The local model endpoint is fixed to loopback. Its outputs are hypotheses,
   quoted source spans, or code candidates. They cannot select arbitrary hosts,
   commands, file destinations or authority. Model/source instructions are data.
3. The portable analysis-kit builder executes only its fixed trusted template.
4. An explicit `--build-spec` additionally enables the versioned pure-function
   builder. It binds the description and test cases before generation and withholds
   the cases from the model. Its accepted AST language omits imports, IO,
   reflection, classes and arbitrary calls. A separate child has a five-second
   parent timeout, memory limits and a minimal environment. If resource limits
   cannot be installed, evaluation fails. This is a restricted language runner,
   not a general Python/OS sandbox. General software builds require a separately
   configured host executor and remain an open action request.
5. LAGEFADEN is a named, digest-bound, offline adapter. Its exact MIT sources are
   listed before import. It receives synthetic replay data and has no device link.
6. GitHub input uses bounded GET reads through `gh`. Publishing code is a
   separate developer action. Ingested workspaces and model caches stay private.

## Test contract

Target: temporary directories and pure-function child processes owned by this
test. Inputs: synthetic JSON, fixed local source strings and generated candidate
functions. Data class: PUBLIC_SYNTHETIC. Stop before any external system access,
credential access, uncontrolled process launch or source-code execution.

Meaningful negative controls: executable-looking corpus input creates no marker;
source retraction removes active structural use; source mutation during a build
prevents receipt commit; invented quotes are rejected; repeated quotes retain
all candidate spans; reflected or IO-capable function candidates are rejected;
nonterminating accepted functions hit the child time limit. A passing test binds
only these declared contracts. Full model correctness, OS sandbox security,
source authenticity and a complete universe are separate questions.

Current base: `539990df83ebd690f95528ea9c212d3b9c1eaa25`, preserved in Git.
Development occurs in a separate worktree and branch. Failed builds retain their
candidate and evidence; receipt success and deployment are separate states.

Before delivery the candidate also integrates published Core 1.2.1 commit
`274cbdef652021ccac6ab4297614e95057cf89b9`. Its stable OS-lock protocol, exact
resume binding, source restoration and locked atomic exports are retained.
Finish old 1.2.0 writers before using the 1.2.1/2.0 locking protocol. The combined
local suite has 78 tests; the recorded synthetic workspace verifies after reuse.
