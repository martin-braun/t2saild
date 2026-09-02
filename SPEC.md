# t2saild — Product Contract

## Contract status and document roles

This document is the authoritative contract for `t2saild`. It specifies required
behavior and interfaces. Implementation and validation status are recorded in
the evidence section.

- `SPEC.md` owns contract truth.
- The recorder synchronizes implementation truth in `CONTEXT.md` after the
  contract is final.
- `README.md` owns operator guidance.
- `AGENTS.md` owns onboarding, ownership, routing, safety, and protected
  surfaces.

## Mission

Replace inherited `t2fand` with a short, linear, auditable `t2saild`
battery-sailing daemon:

- POSIX shell, foreground, root-required, single process;
- MIN/MAX battery-window control with hysteresis;
- CPU governor profiles selected from the selected Battery `status` value;
- first-match readable/writable battery-charge-limit (BCLM) sysfs discovery;
- two internal controller states, `charging` and `sailing`, with a separate
  logged-state value permitted only in operational records;
- OpenRC supervision and configuration.

## Scope

In scope:

- the `t2saild` executable and its public CLI;
- strict MIN/MAX validation and startup ordering;
- battery and BCLM discovery, direct reads of charge samples, decimal-integer
  validation, direct writes, and write readbacks;
- the two-state controller and one-second polling loop;
- production CPU cpufreq paths, `cpupower` control, and private fake-root seams;
- handled signal and failure exits with BCLM restoration through one cleanup
  function;
- the OpenRC init script, `conf.d` values, and logger routing;
- target-distribution packaging for the `cpupower` executable;
- project-native acceptance checks for the above behavior.

## Non-goals

- fan, temperature, SMC, GPU, or Python control;
- systemd or any service manager other than OpenRC;
- named threshold options, configuration reload, or generated configuration;
- a separate user-facing full-charge action or compatibility alias;
- battery-health calculation or reading, including `charge_full_design`, or any
  capacity-file dependency;
- a public CLI or persistent controller state for discharging reporting, an AC
  interface, or a separate controller mode;
- AC discovery, governor restoration, governor drift repair, or governor
  persistence beyond the last selected hardware value;
- network APIs, GUI, metrics endpoints, adaptive scheduling, or remote sources;
- an application PID file, PID ownership, PID locking, or PID lifecycle
  contract;
- changes to `AGENTS.md` or `TODO.md` in this task.

## Definitions

- **MIN**: second positional, lower operator-supplied battery percentage.
- **MAX**: first positional, upper operator-supplied battery percentage.
- **PROFILE**: first optional CPU governor profile, used for every nonempty
  one-line Battery status other than exact `Discharging`, and for the first four
  consecutive exact `Discharging` samples.
- **BATPROFILE**: second optional CPU governor profile, used from the fifth
  consecutive exact one-line Battery status `Discharging` sample until a
  non-`Discharging` sample restores `PROFILE`.
- **BCLM**: the first discovered `battery_charge_limit` sysfs attribute. This
  exact path is the readable/writable operative current-limit interface; no
  child or alternate path may be derived from it.
- **current limit**: the freshly read, validated value from BCLM.
- **capacity**: the usable percentage derived for each fresh charge sample as
  integer `100 * charge_now / charge_full`, truncated toward zero. It drives
  startup selection and runtime transitions under REQ-110 and REQ-111. No
  capacity file or health value is used.
- **controller state**: the internal policy state, exactly `charging` or
  `sailing`. No other value is permitted internally or in transition `from` or
  `to` fields.
- **charging**: policy state that charges toward logical `MAX` and whose
  required BCLM target is `MAX+1`. The compensation is a BCLM target only; it is
  not part of capacity derivation or threshold comparison.
- **sailing**: policy state in which charging is disabled while AC remains
  connected. Its required BCLM target is `MIN - 1`. This policy description is
  not a hardware guarantee.
- **logged state**: the `state` field in a startup, verbose poll, or transition
  record. It is `charging`, `sailing`, or `discharging`; `discharging` is a
  reporting value only and is never an internal controller state.
- **handled exit**: normal termination, signal-requested normal exit, or
  controlled failure after BCLM control has been attempted.
- **private test inputs**: subprocess environment inputs for a temporary sysfs
  root override, a finite poll limit, and zero delay; each is copied immediately
  into a lowercase runtime variable. They are not a production CLI or library
  interface.
- **governor**: the current CPU frequency governor exposed by the production
  `scaling_governor` path. The requested profiles are complete tokens from
  `scaling_available_governors`.

## Stable requirements

Requirement IDs are stable. Historical `t2fand` material is not an active
requirement and does not constrain these requirements.

### Identity and CLI

- **REQ-100** — **Changed.** `t2saild` is a short, linear, auditable executable
  POSIX `/bin/sh` script. It runs in the foreground as one normal process, uses
  one cleanup function, and uses no Bash-only syntax, Python, or alternate
  runtime.
- **REQ-101** - **Changed.** The public invocation is:
  `t2saild [-v|--verbose] [-V|--version] [-h|--help] MAX MIN [PROFILE BATPROFILE]`.
  `MAX` and `MIN` are positional operands in that order. `PROFILE` and
  `BATPROFILE` are optional only as a pair; when both are omitted they default
  to `performance` and `powersave`, respectively. `-V` prints the version and
  exits successfully. `-h` and `--help` are equivalent help actions and exit
  successfully without performing battery control.
- **REQ-102** — No named threshold option is part of the public interface.
  Options are accepted only before positional operands. Unknown options, missing
  operands, extra operands, a lone profile, and malformed operands fail with a
  diagnostic and nonzero status. Two positional operands use the profile
  defaults; four positional operands use the supplied profile pair.
- **REQ-103** — MIN and MAX are validated directly with quoted POSIX `test`
  integer comparisons: `[ "$MIN" -ge 20 ]`, `[ "$MIN" -lt "$MAX" ]`, and
  `[ "$MAX" -le 99 ]`. A failed comparison makes the operands invalid. These
  comparisons must enforce exactly `20 <= MIN < MAX <= 99`; no decimal pre-scan
  or numeric normalization is performed. Validation occurs before root-dependent
  control, discovery mutation, or BCLM writes. After options are consumed, the
  positional mapping is `MAX=$1` and `MIN=$2`.
- **REQ-104** — **Changed.** Root is mandatory for production control on `/sys`.
  A non-root control start fails nonzero before battery discovery or BCLM
  mutation. The overridden fake sysfs root is canonicalized before UID gating
  using POSIX shell canonicalization; an external `realpath` utility is not
  required. Executable control tests may bypass the uid-0 gate only when its
  canonical root is other than `/sys`. An alias canonicalizing to `/sys` remains
  root-required and fails before discovery. This override is not a CLI option or
  user-facing environment interface and must not relax the production root
  requirement.

### Discovery and BCLM I/O

- **REQ-105** — **Changed.** Production discovery searches `/sys/devices/**/`
  and selects the first `battery_charge_limit` path yielded by that search. With
  a private test root, the same search is rooted at `<root>/devices`. Zero
  matches are control errors. The selected path itself is used for every current
  limit read, control write, and readback; no child or alternate path is
  derived. Additional matches are not counted, deduplicated, or rejected. The
  root input is a private subprocess test seam, not a production CLI or operator
  environment interface.
- **REQ-106** — **Changed.** The daemon scans Linux power-supply entries and
  selects the first directory whose directly read `type` is `Battery`. It
  retains that selected directory and directly reads its `charge_now` and
  `charge_full` attributes for each capacity sample. It does not discover, read,
  or validate a `capacity` attribute/file or any battery-health value. Missing,
  unreadable, or invalid charge inputs are control errors. Alias resolution,
  deduplication, and ambiguity rejection are not performed. A selected entry
  with invalid charge inputs is not replaced by a later entry.
- **REQ-107** — **Changed.** BCLM current-limit reads are direct reads from the
  selected path. Each current-limit value must be a nonempty, single-line POSIX
  decimal integer in the inclusive range 0–100. The daemon must validate the
  nonempty decimal-integer read with POSIX shell `case` digit-class matching
  (rejecting an empty value or any value containing a non-digit), then validate
  the range. Empty, unreadable, multiline, non-decimal, or out-of-range values
  are fatal control errors; no sentinel, fallback, or numeric normalization is
  used. Each `charge_now` and `charge_full` read must likewise be a nonempty,
  single-line POSIX decimal integer validated with the POSIX shell `case`
  digit-class match. `charge_now` must be nonnegative, `charge_full` must be
  strictly positive, and `charge_now` must be less than or equal to
  `charge_full`; these validations occur before capacity derivation. Empty,
  unreadable, multiline, non-decimal, zero-full, or `charge_now > charge_full`
  values are fatal control errors under the existing capacity/read failure
  semantics. Capacity is then exactly integer `100 * charge_now / charge_full`,
  truncated toward zero, with no `+1`, clamp, or fallback. `charge_full_design`
  is not read.
- **REQ-108** — **Changed.** BCLM writes are direct writes to the selected path,
  followed by a direct readback from that same path. The readback is validated
  under REQ-107 and must equal the requested target. Every write target must be
  one of the validated `{MIN-1, MAX+1, 100}` values; `MAX+1` is the charging
  compensation for logical `MAX` and is valid because REQ-103 caps MAX at 99.
  `MIN-1` is the sailing target; with the lower bound `MIN=20`, its lowest
  target is `19`, within the BCLM range. A failed write, failed readback, or
  readback mismatch is a control or cleanup error as applicable. No persistent
  BCLM file descriptor is retained.

### Policy and lifecycle

- **REQ-109** — The controller has exactly two steady states: `charging` and
  `sailing`. In `charging`, logical MAX maps to required BCLM target `MAX+1`; in
  `sailing`, required BCLM target is `MIN-1`. Internal controller state remains
  exactly one of these two values; `discharging` is not a controller state.
- **REQ-110** — **Changed.** Startup directly reads and validates the current
  limit and takes one capacity sample from `charge_now` and `charge_full`. It
  selects internal `charging` with BCLM target `MAX+1` when capacity is `< MAX`,
  otherwise (`capacity >= MAX`) selects internal `sailing` with BCLM target
  `MIN-1`. Thus startup comparison is inclusive at MAX for sailing. It then
  writes and reads back that BCLM target. An invalid startup charge sample fails
  before BCLM control is attempted.
- **REQ-111** — **Changed.** The daemon polls once per second. It retains the
  first-selected battery and BCLM paths during the run, directly reads and
  validates the current limit from the selected BCLM path on every sample, and
  rereads both `charge_now` and `charge_full` for each fresh capacity sample. It
  does not rediscover interfaces, count aliases, or perform a separate
  external-drift repair action. Capacity is the sole charge-policy sensor; BCLM
  current limit and Battery status cannot select or transition controller state.
  Each poll applies this order: read and validate BCLM current limit; read and
  validate both charge inputs and derive capacity; apply capacity hysteresis
  and, when required, write/read back the new BCLM target before committing the
  new state; read Battery `status` once, update the Discharging debounce, and
  determine the logged state; emit any transition record when applicable, then
  the verbose poll record; then inspect the current governor and conditionally
  change and verify the selected profile. After a successful current-governor
  validation finds a mismatch, the daemon emits the exact setprofile record
  defined in REQ-124 immediately before the `cpupower` attempt. This attempt
  record is unconditional with respect to quiet mode. Governor inspection and
  profile changes occur after the transition and poll records. Equality emits no
  setprofile record or command. The capacity transitions are: while `charging`,
  capacity `>= MAX` selects `sailing` with target `MIN-1`; while `sailing`,
  capacity `< MIN` selects `charging` with target `MAX+1`. `MIN` remains the
  exclusive lower capacity hysteresis threshold and is not the sailing BCLM
  target. Equality at MIN retains the prior state; equality at MAX retains
  `sailing` or transitions `charging` to `sailing`, as applicable. After a
  transition, subsequent polls evaluate only the condition for the new state. An
  invalid charge sample, status result, or governor operation is fatal; after
  control has been attempted, the existing `EXIT` cleanup restores BCLM=`100`.
- **REQ-112** — **Changed.** One `EXIT` trap, installed before the first BCLM
  control write, invokes the single cleanup function. SIGINT and SIGTERM cause
  normal exit and perform no I/O in their signal handling. Cleanup is not
  implemented through request flags or a required main-path cleanup call.
  Successful startup and state/control outcomes use the stable key=value records
  in REQ-124. Failure and shutdown outcomes remain direct and promptly visible.
- **REQ-113** — **Changed.** On every handled exit after BCLM control has been
  attempted, the cleanup function directly writes BCLM=`100` to the selected
  path and directly reads it back. A valid readback must equal `100` and is
  reported. A restoration write, readback, or verification failure is reported
  and makes the exit nonzero; cleanup remains one-shot.
- **REQ-114** — **Changed.** Abrupt termination that prevents trap execution
  cannot run cleanup. SIGKILL, power loss, kernel failure, and interpreter
  failure therefore cannot be relied on to restore BCLM.
- **REQ-115** — The daemon has no application PID-file, PID-ownership,
  PID-locking, or PID-cleanup requirement. OpenRC may supervise the foreground
  process without adding an application PID contract.

### OpenRC integration

- **REQ-116** — OpenRC is the sole supported service manager. `t2saild.initd`
  invokes `/usr/bin/t2saild` in the foreground through `supervise-daemon`; it
  must not declare a supervisor pidfile, background the daemon, daemonize it, or
  select another init system.
- **REQ-117** — `/etc/conf.d/t2saild` is shell syntax and supplies explicit
  `t2saild_max`, `t2saild_min`, `t2saild_profile`, `t2saild_batprofile`, and
  optional `t2saild_args` values. The init script forwards the existing optional
  `t2saild_args` first, then the positional operands in exact order MAX, MIN,
  PROFILE, BATPROFILE. It must not translate the operands to named threshold
  options, reverse them, or replace them. Empty `t2saild_args` with shipped
  defaults is equivalent to `MAX MIN PROFILE BATPROFILE`;
  `t2saild_args="--verbose"` is equivalent to
  `--verbose MAX MIN PROFILE BATPROFILE`.
- **REQ-118** — The shipped defaults are `t2saild_max=83`, `t2saild_min=77`,
  `t2saild_profile=performance`, and `t2saild_batprofile=powersave`; they
  satisfy REQ-103 and REQ-129. Logger routing uses
  `/usr/bin/logger -t t2saild -p daemon.info` for stdout and
  `/usr/bin/logger -t t2saild -p daemon.err` for stderr. Logger availability and
  delivery are host-dependent.
- **REQ-119** — Respawn policy is a two-second base delay, at most five respawns
  in 60 seconds, with a two-second respawn-delay step. Explicit stop must
  suppress respawn. Runtime OpenRC directive semantics remain unknown until
  validated on the target.

### Acceptance surface

- **REQ-120** — **Changed.** Acceptance must explicitly test thresholds in
  positional order `MAX MIN`, two-operand profile defaults, four-operand
  explicit profiles, missing and extra operand rejection, lone-profile
  rejection, `-V`, successful equivalent `-h` and `--help` help actions,
  rejection of named threshold options, and the exact inequality
  `20 <= MIN < MAX <= 99` before any BCLM mutation, including rejection of
  MAX=100. It must verify that `t2saild 83 77` defaults to
  `performance`/`powersave` and is equivalent to
  `t2saild 83 77 performance powersave`.
- **REQ-121** — **Changed.** Acceptance must use a private subprocess with
  environment inputs, a fake sysfs root, finite polling, and zero delay. The
  inputs are only a root override, poll limit, and zero delay; each is copied
  immediately into a lowercase runtime variable. A PATH-provided test `cpupower`
  stub is fixture setup, not a daemon input or public interface. It must verify
  configurable- root first-match BCLM discovery, reads, writes, and readbacks on
  the exact selected path; first-match `type=Battery` directory discovery;
  direct `charge_now`/`charge_full` sampling and exact derived capacity
  (including `5773000`/`6829000` producing `capacity=84`); removal or change of
  a capacity file having no effect; rereading both charge inputs on each next
  sample; current-limit reads and validation on every sample; BCLM changes alone
  having no transition or drift repair effect; POSIX decimal-integer validation
  and fatal handling for charge inputs; invalid charge values failing safely
  without startup control mutation and with post-control cleanup restoration;
  startup capacity selection and target; exact truncated capacity with no `+1`
  or clamp; strict capacity threshold transitions with BCLM target `MIN-1`/
  `MAX+1` and equality behavior; BCLM=`MAX+1` in `charging`, BCLM=`MIN-1` in
  `sailing`; `MIN=20` produces sailing target `19` within the BCLM range; the
  permitted BCLM write set exactly `{MIN-1, MAX+1, 100}`; truthful `min` as
  logical MIN and, when sailing is selected, its target/limit/post_limit values
  as actual `MIN-1`; control-write and readback failures; cleanup-write/readback
  failure returning nonzero; handled-exit restoration to BCLM=`100`; and the
  required key=value records. It must verify the selected Battery one-line
  `status` is read once per startup or poll sample; exact `Discharging` emits
  `state=discharging` immediately, while BATPROFILE starts only at the fifth
  consecutive exact `Discharging` sample, counting startup, and saturates until
  a non-`Discharging` sample restores PROFILE and resets the count. Every other
  nonempty one-line value selects PROFILE and logs the internal `charging` or
  `sailing` state. Missing, unreadable, or empty status fails control. Status is
  reused for every record emitted for that sample. Tests must cover no caching,
  debounce startup and poll boundaries, saturation, reset, immediate profile
  restoration, and status independence from controller state, capacity, BCLM,
  hysteresis, control, writes, readbacks, and transition `from`/`to`, plus
  transition `from`/`to` restricted to `charging|sailing` while transition
  `state` may be `discharging`; and the conditional exact setprofile record,
  with its saturated `streak`, mismatch-only emission, immediate pre-command
  position, quiet-mode emission, and no emission on governor-read failure. It
  must verify the observable poll cycle order: a transition record when
  applicable, then the verbose poll record, then governor inspection, and, on
  mismatch, the setprofile record immediately before the `cpupower` attempt.
  Multiline-status rejection or fallback is not required because the endpoint is
  guaranteed one-line.
- **REQ-122** — **Changed.** Daemon acceptance must use executable subprocess
  behavior coverage only. It must verify direct current-limit reads, selected
  `type=Battery` directory discovery, per-sample direct `charge_now` and
  `charge_full` rereads, exact truncated integer capacity derivation, no
  capacity-file or `charge_full_design` dependence, fresh capacity-driven
  startup and runtime transitions with BCLM target `MIN-1`/`MAX+1`, strict
  decimal validation and fatal invalid-charge handling, current-limit reads and
  validation on every sample, BCLM-change independence from transitions, control
  and cleanup readback verification, no per-cycle rediscovery or drift repair,
  strict hysteresis boundaries with MAX-inclusive sailing transition, MIN-
  exclusive charging transition, and interior retention, sailing target `MIN-1`
  including `MIN=20` yielding target `19`, required
  startup/poll/transition/cleanup records, handled-exit cleanup and restoration,
  INT/TERM normal exit, and environment-only test inputs. It must not rely on
  sourceability or assertions about daemon source/text, POSIX syntax,
  cleanup-trap structure, or fan-control text/surface absence. Focused static
  checks are permitted for external OpenRC argument forwarding and package
  surfaces, including the revised operand/default forwarding, dependency, OpenRC
  directives, and logger routing. Acceptance evidence is unknown until
  project-native checks run. It must additionally cover the three logged state
  values versus the exact two-value controller state; one status read per
  startup or poll sample; immediate `state=discharging` for exact `Discharging`,
  PROFILE for its first four consecutive samples, and BATPROFILE from its fifth
  consecutive sample; PROFILE for every other nonempty one-line status; fatal
  missing, unreadable, and empty status; reuse of status for records; no status
  caching; exact five-sample Discharging debounce including startup, immediate
  `state=discharging` logging, saturation, reset, and immediate PROFILE restore;
  and no status influence on controller state, capacity, hysteresis, BCLM,
  writes, readbacks, or transition `from`/`to`. These checks must coexist with
  capacity as the sole charge transition sensor and BCLM as the validated charge
  actuator. It must also cover fake-root CPU paths, `cpupower` availability,
  available-governor token validation, governor-file validation, per-sample
  governor reads, no-command equality, exact `cpupower frequency-set -g TARGET`
  invocation, same-path readback, and fatal command/readback/mismatch failures.
  It must verify one exact setprofile record immediately before each attempted
  governor command, with the validated current governor, passed target, and
  saturated decision streak; no record on equality or governor-read failure;
  quiet-mode emission when a command is attempted; attempt-not-success meaning;
  and fatal command/readback handling with existing BCLM cleanup. It must verify
  that startup, poll, transition, and cleanup record formats remain unchanged,
  that no governor fields are added to them, and that setprofile has no extra
  fields or state field. It must verify that each poll's capacity hysteresis and
  poll record precede governor inspection or profile change, and that profile
  errors remain fatal with BCLM cleanup after control has begun. Multiline
  status rejection or fallback is not required under the one-line endpoint
  guarantee.
- **REQ-123** — **New.** Auditability is an explicit implementation requirement:
  control flow, discovery, reads, writes, signal exits, and cleanup must remain
  inspectable as short linear POSIX shell paths with no hidden runtime or
  general-purpose abstraction layer.

- **REQ-124** — **Changed.** Operational records use one stable key=value
  vocabulary. Successful startup emits `record=startup` with `min`, `max`,
  `limit`, `target`, `capacity`, and `state`; `capacity` is the current sample's
  exact truncated integer `100 * charge_now / charge_full` result, and `limit`
  is the actual validated post-write readback. `min` is the logical MIN
  threshold, not an actuator value; `max` is the logical capacity threshold.
  `target` is the actual BCLM target, therefore `MAX+1` for `charging`, `MIN-1`
  for `sailing`, and `100` for cleanup. Thus a sailing startup's `target` and
  `limit`, and a transition into sailing's `target` and `post_limit`, are the
  actual `MIN-1` value. Every verbose poll emits `record=poll` with those same
  six keys, including polls without transitions. On a no-transition verbose
  poll, `limit` is the freshly read and validated current BCLM value, not a
  write readback; on a transition poll, it is the validated readback of that
  poll's transition target. Every transition emits an unconditional
  `record=transition` with `from`, `to`, `min`, `max`, `pre_limit`, `target`,
  `post_limit`, `capacity`, and resulting `state`, even without verbose mode.
  `pre_limit` is the freshly read and validated current BCLM value before the
  transition write; `post_limit` is the actual validated post-write readback
  transition value. Transition records use `post_limit`, not `limit`. A
  no-transition poll's `limit` remains the freshly read actual current BCLM
  value and is not a write readback. Cleanup that owns restoration emits
  `record=cleanup` with `target=100` and the actual validated post-write
  readback as `limit`. When a validated current governor differs from the
  selected target, immediately before the `cpupower` attempt the daemon emits
  exactly `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>`.
  `from` is that validated current governor, `target` is the governor passed to
  `cpupower`, and `streak` is the saturated Discharging decision streak at the
  attempt. This record records an attempt, not success. It is emitted regardless
  of quiet mode whenever the command is attempted, but never on governor
  equality or governor read/validation failure. Command failure, readback
  failure, and readback mismatch remain authoritative fatal diagnostics, with
  existing BCLM cleanup after control has begun. Existing startup, poll,
  transition, and cleanup formats remain unchanged; setprofile has no additional
  fields and no governor fields are added to those prior record types. Write,
  readback, state, failure, and shutdown outcomes remain promptly visible
  through the existing OpenRC stdout/stderr logger routing. Help documents the
  complete verbose record, unconditional transition records, and the setprofile
  record type. The `state` field is a logged state, not the internal controller
  state field. The selected type=`Battery` directory's `status` endpoint is
  guaranteed to return one nonempty line. For each startup or poll sample, the
  daemon reads that endpoint once and updates an exact consecutive-Discharging
  counter: exact `Discharging` increments it up to five, while every other
  nonempty one-line value resets it to zero. The startup sample counts as the
  first sample. BATPROFILE is selected only when the counter reaches five; the
  fifth and later consecutive exact `Discharging` samples use BATPROFILE. Any
  non-`Discharging` sample immediately restores PROFILE. Missing, unreadable, or
  empty status is a fatal control error. The sample's status result is reused
  for every record emitted for that sample: exact `Discharging` immediately
  emits `state=discharging`, even before BATPROFILE is selected; otherwise the
  current internal `charging` or `sailing` state is emitted. Status is not
  cached between samples and never affects controller state, capacity,
  hysteresis, BCLM, BCLM targets, control, writes, readbacks, or transition
  `from`/`to`. Transition `from` and `to` remain `charging|sailing`, while
  transition `state` may be `discharging`. The daemon does not enumerate
  non-`Discharging` values or perform explicit multiline rejection. No governor
  keys are added to startup, poll, transition, or cleanup records. Cleanup
  remains unchanged and has no `state` field.

- **REQ-125** — **New.** Production CPU governor interfaces are exactly
  `/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors` and
  `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`. Under the private
  fake-root seam they resolve to the equivalent paths below
  `<root>/devices/system/cpu/cpu0/cpufreq`. No AC interface or alternate CPU
  path is discovered.
- **REQ-126** — **New.** Before the first BCLM control write, the daemon must
  require `cpupower` through `PATH`, directly read
  `scaling_available_governors`, validate a nonempty one-line whitespace-
  separated governor list, and require PROFILE and BATPROFILE to equal complete
  list tokens. It must directly read and validate a nonempty one-line current
  `scaling_governor` value. Missing, unreadable, empty, malformed, or
  unavailable startup governor dependencies are fatal and must fail before
  initial BCLM mutation where possible. The target-distribution runtime package
  name is `cpupower`; it provides the required `cpupower` executable.
- **REQ-127** — **Changed.** At startup and on every poll, including quiet
  no-transition polls, the daemon directly reads the selected Battery's one-line
  `status` exactly once and updates the five-sample Discharging debounce in
  REQ-124. Exact `Discharging` increments the saturated counter; every other
  successfully read nonempty one-line value resets it and immediately selects
  PROFILE. BATPROFILE is selected only on the fifth and later consecutive exact
  `Discharging` samples, including a startup sample. Exact `Discharging` is
  logged immediately as `state=discharging`, regardless of the selected profile.
  On a poll, this status/debounce step follows capacity hysteresis and precedes
  the poll record. After that poll record, the daemon reads the current
  `scaling_governor`; if it equals the debounced selected target, it must not
  invoke `cpupower` and emits no setprofile record. Otherwise, after the
  validated read and immediately before the command attempt, it emits exactly
  `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>`, where
  `CURRENT` is that read value, `TARGET` is the governor passed to `cpupower`,
  and `streak` is the saturated decision streak, then invokes exactly
  `cpupower frequency-set -g TARGET`, rereads the same `scaling_governor` path,
  and requires exact target equality. The setprofile record records an attempt,
  not success; command/readback diagnostics remain authoritative and fatal.
  Startup uses the same selected-profile control after its startup record: it
  reads and validates the current governor, emits setprofile only on mismatch,
  then attempts `cpupower` and performs its readback, with the same
  mismatch-only setprofile ordering. The REQ-126 preflight read remains required
  before the first BCLM write. A status read failure (missing, unreadable, or
  empty), governor read or validation failure, unavailable command, command
  failure, readback failure, or readback mismatch is a fatal control error. No
  setprofile record is emitted when the governor read or validation fails. On
  quiet polls, setprofile remains unconditional whenever the command is
  attempted even when the poll record is suppressed. A profile or governor error
  after control has begun invokes the existing cleanup and its BCLM=`100`
  restoration. A status result is reused for all records emitted for that
  sample; it is not reread solely for logging.
- **REQ-128** — **Changed.** Governor selection is independent of the capacity
  controller: `Full` while sailing selects PROFILE, and exact `Discharging`
  while internally charging selects PROFILE for the first four consecutive
  samples, then BATPROFILE from the fifth sample while its logged state is
  already `discharging`. Status can affect only the debounced CPU governor and
  logged `state`; it cannot affect capacity, internal `charging|sailing` state,
  hysteresis, BCLM targets, BCLM control, writes, readbacks, or transition
  `from`/`to`. The last selected governor persists after exit. Cleanup performs
  BCLM restoration only: it never restores a prior governor or repairs governor
  drift.
- **REQ-129** — **New.** OpenRC configuration supplies the four profile-aware
  values `t2saild_max`, `t2saild_min`, `t2saild_profile`, and
  `t2saild_batprofile`; shipped defaults are `83`, `77`, `performance`, and
  `powersave`. The init script forwards optional `t2saild_args` first, followed
  by MAX, MIN, PROFILE, BATPROFILE in that exact order. Existing foreground
  supervision, logger routing, installation modes, and package surfaces remain
  unchanged except for the required `cpupower` runtime dependency.

## Interfaces

| Interface    | Contract                                                                                                                                                                                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CLI          | `t2saild [OPTIONS] MAX MIN [PROFILE BATPROFILE]`; options are exactly `-V`/`--version`, `-v`/`--verbose`, and `-h`/`--help`, with the help options equivalent and successful.                                                                                     |
| BCLM         | First path yielded by the production search matching `/sys/devices/**/battery_charge_limit`; the exact path is readable, writable, and read back after every control write. Charging writes `MAX+1`, sailing writes `MIN-1`, and cleanup writes `100`.            |
| Battery      | First Linux power-supply directory with directly read `type=Battery`; each sample directly reads `charge_now` and `charge_full` and derives capacity for policy and records. No capacity or health attribute is read.                                             |
| CPU governor | Production `cpu0` cpufreq `scaling_available_governors` and `scaling_governor` paths; fake-root equivalents under `<root>/devices`; `cpupower frequency-set -g TARGET` on mismatch, immediately preceded by the conditional setprofile record defined by REQ-124. |
| Records      | Stable `record=startup`, `record=poll`, `record=transition`, and `record=cleanup` formats, plus the conditional exact `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` format, as defined by REQ-124. Existing formats remain unchanged.          |
| Signals      | SIGINT and SIGTERM cause normal exit; one `EXIT` trap invokes cleanup.                                                                                                                                                                                            |
| Test inputs  | Private subprocess environment inputs for root override, finite poll limit, and zero delay; no library interface.                                                                                                                                                 |
| OpenRC       | `/etc/init.d/t2saild`, `/etc/conf.d/t2saild`, and `/usr/bin/t2saild`; foreground `supervise-daemon`.                                                                                                                                                              |
| Package      | Target-distribution runtime dependency `cpupower` provides the required `cpupower` executable.                                                                                                                                                                    |

## Runtime contract

The daemon validates the MAX/MIN positional pair and optional profile pair,
checks root, selects the first battery and BCLM matches, performs the CPU
governor startup preflight in REQ-126, and directly reads and validates the
current limit and one `charge_now` / `charge_full` sample. It validates
non-negative decimal-integer charge inputs with `charge_full > 0` and
`charge_now <= charge_full`, then derives capacity as integer
`100 * charge_now / charge_full` truncated toward zero, with no `+1` or clamp.
An invalid charge input, including invalid ordering, follows the existing fatal
capacity/read failure semantics. Startup selects internal `charging` with BCLM
target `MAX+1` when capacity is below `MAX`, otherwise internal `sailing` with
BCLM target `MIN-1`, and establishes that target through a BCLM write and
readback. It then reads startup status once, updates the five-sample debounce,
emits the startup record, then reads and validates the current governor and,
only on mismatch, emits the exact setprofile record immediately before the
`cpupower` attempt and selects and verifies the CPU governor. The daemon then
polls the retained paths. Each next sample rereads and validates the current
limit and both charge inputs before derivation, applies capacity hysteresis and
any transition write/readback, reads status once, updates the debounce, emits
any transition record, then emits the verbose poll record when verbose mode is
enabled (and suppresses it otherwise), and then performs the REQ-127 governor
inspection and, only on mismatch, the setprofile record, command, and readback
sequence, including on quiet polls. Thus governor inspection and profile change
follow the poll record; setprofile remains emitted whenever a quiet poll
attempts the command. Equality and governor-read failure emit no setprofile
record. The loop uses fresh capacity for these transitions: while `charging`,
capacity `>= MAX` selects `sailing` with BCLM target `MIN-1`; while `sailing`,
capacity `< MIN` selects `charging` with BCLM target `MAX+1`. Equality at MIN
retains the prior state; equality at MAX retains `sailing` or transitions
`charging` to `sailing`, as applicable. BCLM current-limit changes alone never
transition and are not repaired, but BCLM is read and validated every sample. A
handled exit directly restores BCLM=`100` and verifies the readback after
control has been attempted through the single `EXIT` cleanup trap. Writes are
limited to validated MIN-1, MAX+1, and 100 values. The sample status result
supplies every record emitted for that sample: exact `Discharging` immediately
yields `state=discharging`, while the fifth and later consecutive exact
`Discharging` samples select BATPROFILE; earlier such samples use PROFILE, and
any other nonempty status resets the count and immediately restores PROFILE.
Missing, unreadable, or empty status, and all governor/profile failures, are
fatal; post-control failures use the existing BCLM cleanup path. Status never
drives controller state, capacity, hysteresis, BCLM targets, control, writes,
readbacks, or transition `from`/`to`.

No application PID lifecycle is defined. No user-facing action drives the
battery to full; BCLM=`100` is the mandatory handled-exit restoration value.
Cleanup is BCLM-only: it does not restore a prior CPU governor or repair
governor drift, so the last selected governor persists.

## Historical context — superseded

The inherited `t2fand` implementation and its associated fan, temperature, SMC,
Python, configuration, and service assumptions are retained only as migration
history in project context. They are superseded by this contract, are not
acceptance evidence, and must not be copied into active requirements or payload.

## Evidence status

This revision is pre-implementation contract authority. Existing checked-in
source and test definitions may provide prior static evidence for project
surfaces, but they do not establish the revised `MAX <= 99` bound, charging
BCLM=`MAX+1` compensation, sailing BCLM=`MIN-1` target, MAX-inclusive runtime
transition, five-sample Discharging debounce, poll/record/governor ordering, or
revised record values. Implementation of those clauses and their focused
acceptance evidence are unknown until the project-native checks run. Runtime
charge sampling, governor behavior, hardware, privileged operation, OpenRC
behavior, logger delivery, packaging, and installation remain unknown. Source
inspection and checked-in tests are not runtime or hardware evidence.

## Reconciliation decision

This contract resolves the recorder mismatch by defining the operative current
limit through the exact readable/writable first-match `battery_charge_limit`
node, while usable current-charge capacity is derived from the selected
`type=Battery` directory's `charge_now` and `charge_full` on every fresh sample.
The operator request is accepted as the revised contract authority over
conflicting starter clauses. It requires exact truncated capacity with no `+1`
or clamp; `20 <= MIN < MAX <= 99`; capacity as the sole charge-policy sensor;
permitted BCLM writes `{MIN-1, MAX+1, 100}`; logical MAX mapped to charging
`MAX+1`, sailing `MIN-1`, and cleanup `100`; `MIN` retained as the exclusive
lower capacity hysteresis threshold, so sailing-to-charging requires
`capacity < MIN`; and truthful records where `min` is logical MIN while a
selected sailing state has actual `target`, `limit`, and `post_limit` values of
`MIN-1` when written. MAX-inclusive sailing transitions and focused acceptance
coverage remain required. Exact `Discharging` is logged immediately, while
BATPROFILE requires the fifth consecutive sample including startup, with
saturation, reset, and immediate PROFILE restoration. Poll hysteresis and
records precede governor inspection/profile change, and profile/governor errors
remain fatal with BCLM cleanup after control begins. Unchanged first-match,
readback, signal, OpenRC, and ownership rules remain active. This is a
pre-implementation contract decision; no implementation, test result, or
documentation synchronization is claimed.
