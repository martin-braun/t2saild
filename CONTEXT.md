# CONTEXT.md — t2saild implementation context

This file records verified local implementation truth, reasoning, constraints,
validation, and cumulative history for `t2saild`. `SPEC.md` owns the hardened
contract. `README.md` is the concise operator guide. Source inspection is not
runtime evidence; unknown claims stay marked `unknown`.

<!-- SECTION MAP BEGIN -->

- `1. Project identity`: purpose, scope, owners, users, supported targets, and
  explicit non-goals.
- `2. Current state`: shipped behavior, active work, known gaps, and status.
- `3. Architecture`: components, boundaries, data flow, dependencies, and
  reasons for the chosen structure.
- `4. Interfaces`: public and internal APIs, files, protocols, inputs, outputs,
  compatibility rules, and ownership.
- `5. Workflows`: development, configuration, operation, deployment, release,
  migration, recovery, and approval paths.
- `6. Constraints and invariants`: safety laws, supported limits, immutability,
  ordering, portability, and protected surfaces.
- `7. Security`: secrets, trust boundaries, permissions, threat controls, and
  prohibited handling.
- `8. Validation`: required checks, test levels, health signals, fixtures, and
  evidence of success.
- `9. Known failures and decisions`: failure modes, diagnostics, settled
  decisions, superseded paths, and anti-regression memory.
- `10. Maintenance`: monitoring, upgrades, backups, repair, ownership, and
  documentation-sync triggers.
- `11. Agent rules`: routing, edit boundaries, tool rules, and escalation.
- `12. Current summary`: concise verified snapshot and open unknowns.

<!-- SECTION MAP END -->

## 1. Project identity

`t2saild` is a short, linear, auditable foreground, root-required POSIX
`/bin/sh` daemon for Linux on Apple T2 hardware. It maintains derived usable
charge capacity inside a caller-supplied MIN/MAX window and uses
battery-charge-limit (BCLM) as its actuator/readback interface. It selects CPU
governor profiles from the selected Battery's one-line `status`. OpenRC is the
supported service manager.

Users and owners:

- the Linux-on-T2 administrator configures and supervises the service;
- the daemon owns the foreground control process and BCLM writes while running;
- OpenRC owns service supervision and logger routing;
- package consumers receive the executable, init script, and `conf.d` file.

The verified target hardware exposes a Linux power-supply battery and a
readable, writable `battery_charge_limit` attribute below `/sys/devices`.
Production discovery uses the first match for each. BCLM is the operative
upper-charge actuator/readback interface; capacity is the derived current usable
charge percentage and sole charge-policy sensor. Exact hardware models, kernel
behavior, distribution coverage, OpenRC runtime coverage, charge-limit support
outside that interface, and any hardware/aliasing guarantee are `unknown`.

Non-goals: fan, temperature, SMC, GPU, Python, systemd, network, GUI, metrics,
remote control, adaptive scheduling, configuration reload, generated
configuration, user-facing full-charge actions, and an application PID file.

## 2. Current state

### Present implementation

- `t2saild` is an executable POSIX `/bin/sh` script, version `0.1.0`. It runs in
  the foreground as one process and uses no Bash, Python, or alternate runtime.
- The public options are `-V`/`--version`, `-v`/`--verbose`, and `-h`/`--help`.
  The invocation is `MAX MIN [PROFILE BATPROFILE]`; no named threshold option
  exists. The profile operands are optional only as a pair, defaulting to
  `performance` and `powersave`.
- Threshold validation uses direct quoted POSIX `test` integer comparisons:
  `[ "$minimum" -ge 20 ]`, `[ "$minimum" -lt "$maximum" ]`, and
  `[ "$maximum" -le 99 ]`. A failed comparison invalidates the operands; no
  decimal pre-scan or numeric normalization occurs. The comparisons require
  exactly `20 <= MIN < MAX <= 99`. Public validation and root checking precede
  discovery and BCLM mutation.
- Production discovery selects the first `battery_charge_limit` path yielded
  below `/sys/devices`, and the first entry below `/sys/class/power_supply`
  whose directly read `type` is `Battery`. The selected BCLM path is the
  readable/writable operative current-limit interface. Additional matches are
  ignored; aliases are not resolved or deduplicated.
- Current-limit reads are direct reads from BCLM and are validated with POSIX
  shell `case` digit-class matching as nonempty, single-line decimal integers,
  then checked for the inclusive range 0–100. Empty, unreadable, multiline,
  non-decimal, or out-of-range values are control errors; no numeric
  normalization, sentinel, or fallback occurs. The first selected `type=Battery`
  directory supplies nonempty, single-line non-negative decimal `charge_now` and
  `charge_full` inputs on every sample. `charge_full` must be positive and
  `charge_now` must not exceed it; invalid inputs are control errors. Capacity
  is integer `100 * charge_now / charge_full`, truncated toward zero, and drives
  startup selection and runtime transitions.
- Startup reads current limit and one current-charge sample, selects `charging`
  when capacity is below MAX and `sailing` when capacity is at or above MAX,
  then writes the selected state's BCLM target (MAX+1 or MIN-1) and reads it
  back from the same path.
- Charging requires BCLM=MAX+1. Sailing requires BCLM=MIN-1; with AC still
  connected, charging is disabled. BCLM is freshly read and validated each
  sample as actuator/readback data, but it does not select a state, cause a
  transition, or trigger drift repair. The daemon does not read AC state, so
  actual hardware response remains `unknown`; these are policy descriptions, not
  hardware or charge-response guarantees.
- One direct polling loop retains the selected paths, directly reads current
  limit and rereads `charge_now` and `charge_full` for each current-charge
  capacity sample, and changes charging to sailing when capacity is `>= MAX`, or
  sailing to charging only when capacity is `< MIN`. Equality at MIN and
  interior values retain state and target. Each transition writes and reads back
  the new BCLM target before committing the new state. A changed BCLM current
  limit alone does not cause a transition or repair. It does not rediscover
  interfaces. Each poll orders current-limit validation, fresh capacity and
  hysteresis (including any target write/readback), status/debounce, records,
  then governor inspection and conditional profile change/readback.
- Successful startup emits a stable `record=startup`; verbose polling emits a
  complete `record=poll`; every transition emits a complete `record=transition`
  even without verbose mode. A no-transition verbose poll reports freshly read
  current BCLM in `limit`; startup `limit`, transition `post_limit`, and cleanup
  `limit` report actual validated post-write readbacks. Records keep `min` as
  logical MIN; sailing target and limit values are the physical BCLM `MIN-1`,
  charging uses `MAX+1`, and cleanup uses `100`.
- Startup and each poll read `status` once from the selected `type=Battery`
  directory. Exact `Discharging` logs `state=discharging` immediately and
  selects `profile` for the first four consecutive samples, then `batprofile`
  from the fifth sample onward. Every other nonempty one-line value resets the
  count and immediately selects `profile`, logging the internal `charging` or
  `sailing` state. Missing, unreadable, or empty status is fatal. The status
  result is reused for records, is not cached across samples, and cannot affect
  capacity, controller state, hysteresis, BCLM, writes, readbacks, or transition
  `from`/`to`. The endpoint is guaranteed one-line; multiline defensive fallback
  is not an active requirement.
- CPU control uses the fixed `cpu0` cpufreq paths and requires `cpupower` in
  `PATH`. Before the first BCLM write, startup validates the available-governor
  token list and current governor. After the startup record, and after each
  poll's transition/poll records, each sample rereads the current governor. A
  mismatch emits exactly
  `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` immediately
  before attempting `cpupower frequency-set -g TARGET`; this records an attempt,
  not success. `CURRENT` is the validated governor read, `TARGET` is the command
  target, and `streak` is the saturated Discharging decision streak. The record
  is emitted on attempted commands in quiet mode too. Equality emits neither the
  record nor the command; governor-read or validation failure emits no record.
  Exact `Discharging` samples one through four, counting startup, repair drift
  toward PROFILE; sample five and later repair toward BATPROFILE. Failure is
  fatal. Cleanup restores BCLM only, so the final selected governor persists
  after exit.
- The runtime uses lowercase variables and exactly one `cleanup` function. An
  `EXIT` trap is installed before the first BCLM control write; SIGINT and
  SIGTERM exit normally, then the trap performs cleanup. Cleanup directly writes
  BCLM=100 and verifies the readback. Successful restoration emits
  `record=cleanup`; write, readback, state, failure, and shutdown outcomes are
  written through the existing output routing. No hardware timing/order or
  external logger delivery/order is claimed; logger delivery and persistence
  remain unknown.
- `t2saild.initd` invokes `/usr/bin/t2saild` through foreground
  `supervise-daemon`. `t2saild.confd` supplies `t2saild_max=83`,
  `t2saild_min=77`, `t2saild_profile=performance`,
  `t2saild_batprofile=powersave`, and optional `t2saild_args`; forwarding order
  is `MAX MIN PROFILE BATPROFILE`.
- OpenRC logger directives route stdout to
  `/usr/bin/logger -t t2saild -p
  daemon.info` and stderr to
  `/usr/bin/logger -t t2saild -p daemon.err`.
- `Makefile` installs the executable, init script, and `conf.d` file with modes
  0700, 0755, and 0644. `PKGBUILD` declares package version `0.1.0-1`, local
  sources, `linux-t2`, `findutils`, `util-linux`, and `cpupower` dependencies,
  and the `conf.d` file as a backup.
- `tests/test_t2saild.py` defines standard-library subprocess tests for CLI
  validation, capacity-driven startup states, strict MAX-inclusive/MIN-exclusive
  hysteresis, MAX=99 charging target 100, first-match discovery, direct integer
  validation, write readbacks, stable records, cleanup, signals, CPU governor
  selection/readback, exact setprofile attempt records and ordering, and static
  OpenRC/package surfaces. Its private subprocess seam supplies a temporary fake
  root, finite polling, and zero delay. The root is canonicalized before UID
  gating; only a canonical root other than `/sys` permits the test-only uid-0
  bypass. An alias canonicalizing to `/sys` remains root-required before
  discovery. The seam is not a production or operator interface. Status tests
  cover one read per sample, immediate `state=discharging` logging, exact
  five-sample debounce including startup and saturation, reset, and immediate
  PROFILE restoration.

These are static source and test-definition facts. Test execution, privileged
operation, hardware writes, installation, package build, OpenRC lifecycle,
logger delivery, and package output are not verified.

### Gaps and open status

- `make test` is the project-native validation target and remains unexecuted.
- Hardware compatibility, BCLM semantics on target machines, runtime cleanup,
  CPU governor effects, and the effect of unplugging on battery capacity remain
  unverified.
- OpenRC directive support, foreground supervision, explicit-stop behavior,
  respawn behavior, logger receiver delivery, destination, and persistence are
  static or host-dependent and remain `unknown`.
- Installation modes, package staging, package provenance, skipped checksum
  assurance, build output, and release output remain `unknown` until verified.
- Runtime state, prior BCLM, and AC/plug state are not persisted or restored. No
  live configuration reload, rollback procedure, or compatibility alias is
  implemented.
- Abrupt termination that prevents the main cleanup path cannot guarantee
  BCLM=100 restoration.

## 3. Architecture

### Components and boundaries

1. Argument parsing and threshold validation establish the public action,
   verbose flag, `MAX MIN` positional pair, and optional profile pair.
2. Root validation protects control startup. First-match discovery selects one
   BCLM path and one first `type=Battery` path under the supplied sysfs root.
3. Direct reads use POSIX `case` digit-class validation for current limit and
   charge inputs, with range checks for current limit and `charge_full`/
   `charge_now` ordering. Invalid reads fail without numeric normalization,
   sentinel, or fallback. The controller derives capacity and stores local
   state. CPU governor preflight completes before the first BCLM write; the
   controller then directly writes its required target and reads back the same
   path before accepting the result.
4. The one-second loop retains the selected paths, directly reads and validates
   current limit and rereads `charge_now` and `charge_full` for each capacity
   sample, and applies strict capacity hysteresis without rediscovery, alias
   handling, or separate drift repair. It reads the selected Battery `status`
   once per sample, logs exact `Discharging` immediately, selects `profile` for
   its first four consecutive samples, and selects `batprofile` from sample five
   onward. Every other nonempty one-line value resets the count and selects
   `profile`. It emits any transition record and then the poll record when
   verbose before reading the current governor, emits the exact conditional
   setprofile attempt record immediately before a mismatched
   `cpupower frequency-set -g TARGET` attempt, and verifies same-path readback.
   Quiet polls still emit that attempt record; equality and governor-read
   failure do not. Status and governor failures are fatal. The private test seam
   supplies a fake root, finite poll count, and zero delay. The root is
   canonicalized before UID gating; only a canonical root other than `/sys`
   bypasses uid-0 for executable tests, while canonical `/sys` aliases remain
   root-required before discovery.
5. Lowercase runtime variables support one linear lifecycle. One `cleanup`
   function runs from the `EXIT` trap; INT and TERM request normal exit through
   shell traps and perform no I/O in signal handling. Stable startup,
   verbose-poll, unconditional-transition, and cleanup records expose control
   outcomes and verified readbacks.
6. OpenRC forwards optional `t2saild_args` before configured
   `MAX MIN PROFILE
   BATPROFILE` operands, supervises the foreground process,
   and routes its two output streams to `logger`.

### Reasoning

- Short linear paths make control flow auditable; simplicity outweighs extra
  defensive abstraction for this daemon.
- Positional `MAX MIN` operands keep the public surface small and prevent the
  service from translating named threshold options. The optional profile pair
  keeps governor policy configurable without adding named threshold options.
- Startup validation precedes root-dependent work and writes, so invalid input
  cannot mutate BCLM.
- First-match discovery keeps selection linear; later matches are not counted,
  deduplicated, or rejected.
- Direct reads, POSIX `case` digit-class validation, quoted POSIX integer range
  checks, and direct writes followed by same-path readbacks keep operative
  control explicit; invalid reads fail without numeric normalization, sentinel,
  or fallback.
- Retaining selected paths keeps the polling loop linear and avoids per-cycle
  rediscovery or drift repair.
- Two states and asymmetric capacity comparisons provide hysteresis: startup
  selects sailing at or above MAX, while runtime transitions require capacity
  `>= MAX` or `< MIN`; equality at MIN and interior values retain state and
  target. Charging maps logical MAX to physical BCLM MAX+1.
- One `EXIT` cleanup trap avoids I/O from signal handlers and gives handled
  exits a single restoration attempt.
- Stable key=value records make startup, verbose polls, transitions, and cleanup
  auditable; transition records are unconditional. Logged `state` is separate
  from the exactly two-value controller: a fresh exact `Discharging` status read
  can emit `discharging`, while every other nonempty one-line value emits the
  current controller state. The same status selects the CPU governor; it never
  affects charge policy. A final selected governor is left in place because
  cleanup is BCLM-only.

## 4. Interfaces

### Public CLI

The public invocation is:

`t2saild [-v|--verbose] [-V|--version] [-h|--help] MAX MIN [PROFILE BATPROFILE]`

Options are consumed before the positional MAX and MIN operands. Options after
the first positional operand are not accepted. Two operands use
`performance`/`powersave`; four operands use the supplied profile pair. A lone
profile is rejected.

Supported options are exactly:

- `-V` and `--version`: print `t2saild 0.1.0` and exit successfully;
- `-v` and `--verbose`: print complete `record=poll` records with `min`, `max`,
  `limit`, `target`, `capacity`, and `state`; every transition record is printed
  regardless of verbose mode;
- `-h` and `--help`: print usage and exit successfully. Help text is
  daemon-owned; operator documentation carries the logical-MAX versus physical
  BCLM=MAX+1 distinction without editing the daemon help surface.

Each supplied profile must equal a complete token in the available-governor
list. The daemon requires `cpupower` in `PATH`, reads the current governor after
the startup record and after each poll's records, skips the command on equality,
and otherwise emits exactly
`record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` immediately
before attempting `cpupower frequency-set -g TARGET`, followed by same-path
readback. The record means attempt, not success, and remains emitted for an
attempt in quiet mode. No record is emitted on equality or governor-read
failure. The final selected governor is not restored on exit.

Unknown options, missing operands, extra operands, malformed thresholds, and
named threshold options fail nonzero with a diagnostic. Help and version do not
perform battery control. The private `T2SAILD_ROOT`, `T2SAILD_POLL_LIMIT`, and
`T2SAILD_NO_DELAY` seam is test-only. The root override is canonicalized before
UID gating with POSIX shell canonicalization (`CDPATH= cd -P` followed by
`pwd -P`); no external `realpath` utility is required for canonicalization. Only
a canonical root other than `/sys` permits the uid-0 bypass. An alias
canonicalizing to `/sys` remains root-required before discovery. The seam is not
a production CLI or operator environment interface.

### Hardware interfaces

| Interface     | Local truth                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BCLM          | First `battery_charge_limit` path below `/sys/devices`; the exact path is the upper-charge actuator/readback interface, and every control write is read back and validated. Charging targets MAX+1; sailing targets MIN-1.                                                                                                                                                                                                                                      |
| Battery       | First entry whose directly read `type` is `Battery`; each sample rereads non-negative decimal `charge_now` and positive `charge_full`, requiring `charge_now <= charge_full`, then derives usable charge capacity for policy. `status` is read once per startup or poll sample; exact `Discharging` logs immediately, uses PROFILE for samples 1-4, and uses BATPROFILE from sample 5; other nonempty values reset to PROFILE.                                  |
| CPU governor  | Fixed `cpu0` cpufreq paths. After startup/poll records, a mismatch emits `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` immediately before the `cpupower` attempt; the same `scaling_governor` path is read back and must match.                                                                                                                                                                                                              |
| Records       | Stable `record=startup` and verbose `record=poll` use `min`, `max`, `limit`, `target`, `capacity`, `state`; unconditional `record=transition` adds `from`, `to`, `pre_limit`, and `post_limit`; cleanup reports `target=100` and `limit`; a mismatched governor adds only the exact conditional setprofile attempt record. Logged `state` may be `charging`, `sailing`, or exact-status-derived `discharging`; transition `from`/`to` remain controller states. |
| Signals       | SIGINT and SIGTERM cause normal exit; one `EXIT` trap invokes cleanup and handlers perform no I/O.                                                                                                                                                                                                                                                                                                                                                              |
| Runtime state | Process-local `charging` or `sailing`; selected paths are retained; no PID, prior-limit, or AC-state persistence exists.                                                                                                                                                                                                                                                                                                                                        |

### Service and files

| Path or interface     | Local truth                                                                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `/usr/bin/t2saild`    | Foreground executable installed by `Makefile`; source mode 0700.                                                                           |
| `/etc/init.d/t2saild` | OpenRC definition; source mode 0755; foreground `supervise-daemon`.                                                                        |
| `/etc/conf.d/t2saild` | Shell syntax with `t2saild_max`, `t2saild_min`, `t2saild_profile`, `t2saild_batprofile`, and optional `t2saild_args`; installed mode 0644. |
| OpenRC stdout         | `/usr/bin/logger -t t2saild -p daemon.info`.                                                                                               |
| OpenRC stderr         | `/usr/bin/logger -t t2saild -p daemon.err`.                                                                                                |

`command_args` forwards `t2saild_args` before the two conf.d threshold values as
positional MAX then MIN operands, followed by PROFILE and BATPROFILE. Empty
`t2saild_args` therefore yields `MAX MIN PROFILE BATPROFILE`;
`t2saild_args="--verbose"` yields `--verbose MAX MIN PROFILE BATPROFILE`. The
init script declares `supervisor="supervise-daemon"`, `respawn_delay="2"`,
`respawn_max="5"`, `respawn_period="60"`, `--respawn-delay-step 2`, and
`retry="SIGTERM/5"`. It needs `localmount`, softly uses `logger`, and declares
no network, background, daemonization, or supervisor pidfile setting.

## 5. Workflows

### Startup and operation

1. OpenRC forwards `t2saild_args`, when non-empty, before `t2saild_max`,
   `t2saild_min`, `t2saild_profile`, and `t2saild_batprofile` as positional
   operands to the foreground executable.
2. The executable validates the positional pair, canonicalizes the overridden
   fake root before UID gating, then checks effective UID 0 for production
   `/sys` control. Only a canonical root other than `/sys` permits the private
   test seam to bypass that check; aliases canonicalizing to `/sys` remain
   root-required before discovery. It only then discovers interfaces.
3. It selects the first BCLM and first `type=Battery` entry, directly reads and
   validates current limit and one current-charge sample, and selects `charging`
   below MAX or `sailing` at or above MAX using derived usable charge capacity.
   CPU governor preflight completes before initial BCLM control.
4. It directly writes BCLM=MAX+1 in charging or BCLM=MIN-1 in sailing, then
   reads back and validates the same path. It reads selected-Battery `status`
   once; exact `Discharging` logs `state=discharging` immediately, uses PROFILE
   for samples one through four, and uses BATPROFILE from sample five onward.
   Every other nonempty one-line value resets the count and immediately selects
   PROFILE. Missing, unreadable, or empty status fails. It then emits the exact
   setprofile attempt record immediately before a mismatched governor command
   and verifies the selected governor, leaving the final selection in place on
   exit. Equality and governor-read failure emit no setprofile record.
5. It polls once per second on the retained paths. Each cycle reads and
   validates current limit, rereads `charge_now` and `charge_full`, applies
   strict capacity hysteresis and any transition write/readback, reads `status`
   once and updates its debounce, emits any transition record and then the poll
   record when verbose, then reads the governor and on mismatch emits the exact
   setprofile attempt record immediately before `cpupower`, with same-path
   readback. Quiet polls still emit the setprofile record when a command is
   attempted; equality and governor-read failure do not. It does not rediscover
   interfaces or repair BCLM drift. The sample status is reused for records;
   `from` and `to` remain controller states.

With the 77/83 defaults, startup capacity below 83 selects charging and capacity
at or above 83 selects sailing. Runtime charging changes to sailing at or above
83; sailing changes to charging only below 77. Equality at 77 and all interior
capacity values retain state and target. Charging uses physical BCLM target 84;
sailing uses BCLM target 76. BCLM readbacks report the actuator result but do
not select a state or transition.

### Unplug workflow

The daemon reads battery type and current-charge inputs for capacity policy, and
selected-Battery `status` to select the CPU governor and logged state; it does
not read or persist an AC plug-state input. Exact single-line `Discharging` logs
`state=discharging` immediately; PROFILE applies to samples one through four and
BATPROFILE from sample five. Every other nonempty one-line value resets the
count and immediately selects PROFILE. Missing, unreadable, or empty status
fails. An administrator may start the configured service and unplug external
power, but charge/discharge response is hardware-dependent and `unknown`. Policy
uses derived usable charge capacity: charging requires BCLM=MAX+1, sailing
requires BCLM=MIN-1, and runtime transitions require capacity `>= MAX` or
`< MIN`.

### Shutdown and recovery

SIGINT, SIGTERM, normal completion, and controlled failures after BCLM control
has been attempted exit through the `EXIT` trap. The single cleanup function
directly writes BCLM=100, reads it back from the same path, emits the cleanup
record on successful restoration, reports failures, continues after a cleanup
failure, and makes the exit nonzero when restoration fails. Cleanup is one-shot.

SIGKILL, power loss, kernel failure, interpreter failure, and other abrupt
termination can prevent restoration. No previous BCLM value is saved for
rollback. OpenRC respawn and explicit-stop semantics are source-level intent;
target lifecycle behavior is `unknown`.

### Installation and service administration

`Makefile` has no compilation step. Its `install` target stages:

- `t2saild` at `$(DESTDIR)$(BINDIR)/t2saild`, defaulting to `/usr/bin`;
- `t2saild.initd` at `$(DESTDIR)$(OPENRC_INITDDIR)/t2saild`, defaulting to
  `/etc/init.d`;
- `t2saild.confd` at `$(DESTDIR)$(OPENRC_CONFDIR)/t2saild`, defaulting to
  `/etc/conf.d`.

Installation performs no service action. The administrator sets
`t2saild_max=83`, `t2saild_min=77`, `t2saild_profile=performance`, and
`t2saild_batprofile=powersave` in `/etc/conf.d/t2saild`, then may use:

- `rc-update add t2saild default` to enable boot start;
- `rc-service t2saild start` to start;
- `rc-service t2saild status` to inspect service state;
- `rc-service t2saild stop` to request restoration and stop;
- `rc-service t2saild restart` to reload conf.d values through a restart.

These service commands, staged paths, and package declarations are static
evidence. Installation, OpenRC execution, and package results are `unknown`.

### Package and release

`PKGBUILD` declares `t2saild` version `0.1.0`, release `1`, target `x86_64`,
GPL3, local sources (`t2saild`, `t2saild.initd`, `t2saild.confd`, `Makefile`),
dependencies `linux-t2`, `findutils`, `util-linux`, and `cpupower`, and
`backup=('etc/conf.d/t2saild')`. It stages through
`make DESTDIR="$pkgdir"
install`. Checksums are skipped. No package build or
release result is claimed.

## 6. Constraints and invariants

- Production control on `/sys` requires effective UID 0. The private fake-root
  subprocess seam canonicalizes its overridden root before UID gating; it
  bypasses uid-0 only for executable tests when that root is other than `/sys`.
  Aliases canonicalizing to `/sys` remain root-required before discovery. Help
  and version actions do not require root because they do not control hardware.
- MIN and MAX use direct quoted POSIX `test` integer comparisons:
  `[ "$minimum" -ge 20 ]`, `[ "$minimum" -lt "$maximum" ]`, and
  `[ "$maximum" -le 99 ]`. A failed comparison invalidates the operands. No
  decimal pre-scan or numeric normalization occurs; the required range is
  exactly `20 <= MIN < MAX <= 99`. Validation occurs before discovery mutation
  or any BCLM write.
- Production discovery selects the first BCLM and first `type=Battery` entry.
  Later matches are not counted, deduplicated, or rejected.
- Current limit is directly read from the selected BCLM and validated with POSIX
  shell `case` digit-class matching as a nonempty, single-line decimal integer,
  then checked in 0–100. Each sample directly rereads nonempty, single-line
  decimal `charge_now` and `charge_full`; the former is non-negative, the latter
  is positive, and `charge_now <= charge_full` is required. Capacity is
  truncated integer `100 * charge_now / charge_full`, truncated toward zero. A
  failed read or invalid value never becomes a policy value, sentinel, or
  fallback; no numeric normalization occurs.
- The steady-state set is exactly `{charging, sailing}`. Charging requires
  BCLM=MAX+1; sailing requires BCLM=MIN-1. At startup, capacity `< MAX` selects
  charging and capacity `>= MAX` selects sailing. Runtime capacity `>= MAX` or
  `< MIN` transitions state; equality at MIN and interior values retain state
  and target. BCLM is freshly read and validated each sample for
  actuator/readback reporting, but it does not transition policy.
- Logged `state` is `charging`, `sailing`, or `discharging`. Startup and each
  poll read the selected Battery `status` once; exact `Discharging` emits
  `discharging` immediately, uses PROFILE for its first four consecutive
  samples, and uses BATPROFILE from the fifth sample onward. Every other
  nonempty one-line value resets the count and immediately selects PROFILE and
  emits the controller state. Missing, unreadable, or empty status is fatal. The
  sample result is reused for records and is not cached. Status cannot affect
  startup selection, controller state, hysteresis, BCLM policy, writes,
  readbacks, capacity, or transition `from`/`to`; cleanup has no state. The
  status endpoint is guaranteed one-line.
- CPU governor control requires `cpupower` and complete PROFILE/BATPROFILE
  tokens from `scaling_available_governors`. After startup/poll records, each
  startup or poll reads `scaling_governor`; equality skips the command and the
  setprofile record, while mismatch emits exactly
  `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` immediately
  before `cpupower frequency-set -g TARGET` and requires same-path readback. The
  record is unconditional for an attempted command, including quiet polls, and
  means attempt, not success. Governor-read failure emits no record. Failure is
  fatal. Cleanup never restores the governor, so the final selected value
  persists.
- BCLM writes are direct writes to validated MIN-1, MAX+1, or 100 values,
  followed by a validated readback from the exact selected path. Selected paths
  are retained during the run.
- A handled exit after control is attempted requires a direct BCLM=100 cleanup
  write and matching readback. Abrupt termination is outside that guarantee.
- The process is foreground, single-process, short linear POSIX shell with
  lowercase runtime variables, exactly one cleanup function, and no application
  PID-file, PID ownership, or PID locking contract.
- Configuration persists as the OpenRC conf.d file. Thresholds and governor
  profiles are configured there; controller state, prior BCLM, governor, and
  plug state are runtime inputs/state, not persisted daemon state. Logger
  persistence belongs to the host receiver.
- The daemon does not claim fan, temperature, SMC, GPU, systemd, network, GUI,
  metrics, adaptive scheduling, or remote-source behavior.
- OpenRC is the only supported service manager. Runtime directive semantics and
  host service behavior remain `unknown` until target validation.

## 7. Security

The daemon is a root process with authority to discover and write the selected
BCLM sysfs attribute. The local administrator controls `/etc/conf.d/t2saild` and
service actions. Permissions, ownership hardening, and target-kernel write
policy are `unknown`.

No authentication layer, encryption, secret store, network listener, metrics
endpoint, or remote source exists in the checked-in daemon. Do not add or expose
secrets. Do not treat logger delivery, package metadata, skipped checksums, or
README examples as runtime-safety evidence.

The private fake-root subprocess seam canonicalizes its overridden root before
UID gating and bypasses uid-0 only for tests when the canonical root is other
than `/sys`. Aliases canonicalizing to `/sys` remain root-required before
discovery. Production `/sys` control remains root-required. The seam must not
become an operator-facing environment or CLI control path.

## 8. Validation

### Evidence available

Static inspection covered `t2saild`, `t2saild.initd`, `t2saild.confd`,
`Makefile`, `PKGBUILD`, `tests/test_t2saild.py`, `README.md`, `CONTEXT.md`, and
`SPEC.md`. It records the available daemon, service, package, and test
definitions. It does not verify execution.

`make test` is the documented project-native test target. It was not executed in
this documentation sync. No passing test, build, install, package, privileged
hardware, service, logger, or release result is claimed.

### Test-definition coverage

The test file defines executable subprocess behavior tests for daemon logic:

- `-h`/`--help`, `-V`, verbose parsing, unknown/missing/extra arguments, named
  threshold rejection, `MAX MIN` order, default profiles, explicit profile
  pairs, lone-profile rejection, and threshold-input behavior;
- startup charging/sailing selection from capacity boundaries and current-charge
  samples;
- strict capacity charging-to-sailing at or above MAX and sailing-to-charging
  below MIN, including equality retention and MAX=99 target 100;
- first-match BCLM and battery discovery, direct current-limit and charge-sample
  validation, exact truncated capacity derivation, capacity-policy selection,
  write/readback results, selected-interface failures, and cleanup restoration;
- handled-exit cleanup, one-time BCLM=100 restoration, cleanup failure
  reporting, stable startup/poll/transition/cleanup records, INT/TERM normal
  exit behavior, and finite private test injection;
- fresh selected-Battery `status` reads for startup and poll samples, immediate
  `Discharging` logged-state output, streak-driven PROFILE/BATPROFILE selection
  across startup counting, the fourth/fifth-sample boundary, and saturation,
  PROFILE restoration on reset, PROFILE selection for other nonempty values,
  fatal missing or empty status, no status caching, and status independence from
  controller state, BCLM policy, hysteresis, capacity, cleanup, and transition
  `from`/`to`;
- fake-root CPU paths, `cpupower` availability, available-governor and current
  governor validation, profile selection, equality command suppression, exact
  setprofile `from`, `target`, and `streak` attempt fields immediately before
  the governor command, quiet-poll mismatch visibility without a poll record,
  same-path readback, command/readback failures with BCLM cleanup, and cleanup
  write-failure reporting.

Static coverage covers intentional external OpenRC forwarding of optional
existing `t2saild_args` when present, followed by `MAX MIN PROFILE BATPROFILE`,
and package surfaces, including OpenRC directives and logger routing. Active
coverage makes no daemon source-structure assertions.

### Pending validation

Runtime hardware behavior, charge response after unplugging, BCLM authority, CPU
governor effects, signal cleanup, abrupt failure, OpenRC syntax and lifecycle,
respawn bounds, logger delivery/persistence, installation, package
staging/build, release output, and compatibility coverage remain `unknown`.

No README command or snippet was executed.

## 9. Known failures and decisions

### Known failure modes

- Invalid threshold text or ordering fails before root-dependent control.
- Non-root production control startup on `/sys` fails before battery discovery
  or BCLM mutation. The private fake-root subprocess seam canonicalizes its
  overridden root before UID gating; only a canonical root other than `/sys` is
  the test-only uid-0 exception. Aliases canonicalizing to `/sys` remain
  root-required before discovery.
- Missing BCLM or battery interfaces, or an unreadable or invalid selected
  current limit or charge input, fail control. Later matches do not replace a
  selected entry.
- A failed direct BCLM write, failed readback, or readback mismatch is fatal for
  control or cleanup as applicable. Current-limit drift is freshly read and
  validated each cycle for actuator/readback reporting, but does not cause a
  transition or separate repair action.
- A handled post-control failure attempts BCLM=100 cleanup. Cleanup failure
  preserves the original failure diagnostic and makes the result nonzero.
- SIGKILL, power loss, kernel/interpreter failure, and other abrupt exits can
  leave the last hardware limit in place.
- Hardware with no supported BCLM, no `type=Battery` entry, or unsupported
  power-supply behavior cannot satisfy startup. Multiple matches use the first
  selected entry; their runtime behavior remains hardware-dependent.
- A selected Battery `status` read that is missing, unreadable, or empty fails
  control. Exact `Discharging` emits `state=discharging` immediately, uses
  PROFILE for the first four consecutive samples, and uses BATPROFILE from the
  fifth sample onward. Every other nonempty one-line value resets the count and
  immediately selects PROFILE and emits the controller state. The endpoint is
  guaranteed one-line, so no multiline fallback is required.
- Missing or invalid CPU governor dependencies, unavailable profiles, failed
  `cpupower` commands, and governor readback mismatches fail control. A
  setprofile record is emitted only after successful current-governor validation
  and immediately before the attempted command; command, readback, or mismatch
  failure after control begins invokes BCLM=100 cleanup. Cleanup restores BCLM
  only; it does not restore the prior governor.

### Settled decisions

- Use positional `MAX MIN [PROFILE BATPROFILE]` operands and exactly the public
  options documented in `SPEC.md`; reject named threshold options and lone
  profiles. Omitted profiles default to performance/powersave.
- Enforce `20 <= MIN < MAX <= 99` before root, discovery, or writes.
- Use exactly two steady states. Startup uses derived usable charge capacity:
  below MAX charges and at/above MAX sails. Runtime capacity at or above MAX
  changes charging to sailing; capacity below MIN changes sailing to charging.
  Equality at MIN and interior values retain state and target. Charging targets
  BCLM=MAX+1; sailing targets BCLM=MIN-1. MIN remains the exclusive lower
  capacity hysteresis threshold, not the sailing actuator target.
- Select the first BCLM and first `type=Battery` entry. Directly read and
  validate current limit and nonempty, single-line decimal charge inputs with
  POSIX `case` digit-class matching; require positive `charge_full` and
  `charge_now <= charge_full`, then derive truncated integer
  `100 * charge_now / charge_full`. Failed reads or comparisons invalidate the
  value, with no numeric normalization, sentinel, or fallback. Directly write
  required BCLM values and verify same-path readbacks.
- Restore BCLM=100 on every handled post-control exit; do not save or restore a
  prior limit and do not expose a separate full-charge action.
- Keep signals side-effect-free and cleanup in one `EXIT` trap.
- Keep the daemon foreground and leave process lifecycle supervision to OpenRC;
  define no application PID contract.
- Keep AC/plug state outside the interface. Derived usable charge capacity is
  the sole state input; BCLM is the upper-charge actuator/readback interface and
  is freshly read and validated each sample without causing transitions or drift
  repair.
- Select CPU governors from the selected Battery's status: exact `Discharging`
  uses PROFILE for its first four consecutive samples and BATPROFILE from the
  fifth; every other nonempty one-line value resets the count and immediately
  uses PROFILE. Read status once per startup or poll sample, reuse it for
  records, and keep it out of capacity, hysteresis, controller state, BCLM
  targets, writes, readbacks, and transition `from`/`to`. After startup/poll
  records, emit exactly one setprofile attempt record immediately before each
  mismatched governor command, including quiet polls; emit none on equality or
  governor-read failure. Leave the final selected governor in place.
- Keep status-derived `discharging` limited to emitted startup, verbose-poll,
  and transition `state`; retain exactly two controller states, with transition
  `from` and `to` restricted to `charging` and `sailing`. Read status once per
  startup or poll sample, reuse it for that sample's records, and use it only
  for CPU governor selection and logged state. Keep it out of charge policy and
  cleanup.
- Treat source/test inspection and project-native commands as evidence
  boundaries, not runtime results.

### Superseded log-only status model

Prior verified behavior established exactly two controller states: `charging`
and `sailing`, selected and transitioned by current BCLM limits under the
previous policy now superseded below. Its existing hysteresis, BCLM policy,
writes, readbacks, capacity, and cleanup rules remain recorded here as history.
The prior verified logging rule was separate: each startup, verbose-poll, and
transition record freshly read the selected Battery `status`; exact single-line
`Discharging` overrode only emitted `state` to `discharging`. Every other,
missing, unreadable, empty, malformed, or multiline result silently fell back to
the controller state. No status cache existed; transition `from`/`to` stayed
controller states, and cleanup stayed state-free. This log-only status model is
superseded: the same one-line status now selects PROFILE or BATPROFILE for CPU
control, while its inability to affect charge state, capacity, hysteresis, BCLM,
writes, readbacks, or transition `from`/`to` remains.

The current endpoint is guaranteed to return one nonempty line. Missing,
unreadable, or empty status is fatal; explicit multiline rejection or fallback
is not required. The selected status is read once per startup or poll sample and
reused for all records from that sample.

### Superseded profile-command observability

Before the current implementation, profile changes had no dedicated
profile-command record. `cpupower` per-CPU output was insufficient to prove the
daemon's selected target: it could show per-CPU observations, but not the
validated `CURRENT`, passed `TARGET`, saturated Discharging streak, or the
command-attempt boundary for the daemon's decision. The implementation now emits
exactly `record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` after
the startup/poll records and immediately before each mismatched `cpupower`
attempt. It emits in quiet mode when a command is attempted, never on equality
or governor-read failure, and records an attempt rather than success. The
existing exact five-sample debounce remains: PROFILE serves samples one through
four, including startup, and BATPROFILE serves sample five onward. Command,
readback, or mismatch failure remains fatal and uses BCLM=100 cleanup after
control begins. No hardware timing/order or external logger delivery/order is
inferred from the record; those remain unknown.

### Superseded blanket test root-gate wording

Earlier context stated that every control startup required effective UID 0. The
implementation and REQ-104 now narrow that boundary: production `/sys` control
remains root-required, while executable tests may bypass uid-0 only through the
private fake-root subprocess seam after its override canonicalizes to a root
other than `/sys`. An alias canonicalizing to `/sys` remains root-required
before discovery. Validation still precedes the root check. Runtime execution
remains unverified.

### Superseded scaffold history

The repository was inherited from `t2fand`, a Python fan/temperature control
scaffold with unrelated SMC, fan, and configuration assumptions. That scaffold
is superseded by the battery-sailing implementation and contract. Its behavior,
files, options, tests, and service assumptions are not current behavior,
acceptance evidence, or compatibility requirements. It is retained here only as
explicit migration history.

### Superseded MIN MAX operand order

The earlier public invocation used positional `MIN MAX`, with MIN first. The
finalized contract explicitly supersedes that order: the public and OpenRC
invocation is `MAX MIN [PROFILE BATPROFILE]`. Two operands default to
`performance`/`powersave`; profiles are accepted only as a pair. Threshold
validation in that superseded state remained exactly `20 <= MIN < MAX <= 100`;
the current contract supersedes that bound with `20 <= MIN < MAX <= 99`.

### Superseded `t2saild_args` omission

An earlier recorder state said that `command_args` omitted `t2saild_args`. That
was a recorder mismatch resolved by the finalized SPEC: existing optional daemon
arguments must be forwarded before positional operands. The prior forwarded
order was MIN MAX; the current init script forwards MAX MIN PROFILE BATPROFILE,
while empty args preserve those defaults.

### Superseded capacity-file interpretation

An earlier verified implementation read the battery `capacity` file and used
that value to select states and drive transitions, while writing BCLM without
reading back the result. It was policy input, not merely informational data.
That behavior is retained as superseded history, not active truth. Its
intermediate successor removed the kernel capacity-file input and derived usable
capacity from fresh `charge_now` and `charge_full` inputs, but treated that
derived value as informational under the then-current BCLM-driven policy. It was
not yet the capacity-driven policy recorded separately below. Earlier wording
that made the capacity-file interpretation directly succeed to that policy was
inaccurate.

### Superseded `+1` capacity workaround

An earlier workaround added one percentage point to the displayed or derived
capacity while charging. That altered the reported value and was not truthful.
It is superseded: displayed capacity remains the exact truncated
`100 * charge_now / charge_full` result in every state. The one-point adjustment
now applies only to the charging actuator target: logical MAX writes physical
BCLM=MAX+1, allowing the hardware path to reach logical MAX without changing
displayed capacity. This rationale is not hardware verification; hardware
response remains `unknown`.

### Superseded sailing actuator target

An earlier sailing policy used BCLM=MIN; with the shipped defaults, that meant
target 77. This target is retained as superseded history. The current sailing
target is BCLM=MIN-1 (76 with the shipped defaults), while MIN remains the
exclusive lower capacity hysteresis threshold. The MIN-1 actuator margin reduces
potential observation of logical-boundary holds/restores; it does not alter
logical capacity derivation, threshold validation, or comparisons. BCLM remains
the upper-charge actuator and capacity the sole state input. Hardware response
and any hardware/aliasing guarantee remain `unknown`.

### Superseded BCLM-driven policy

Previously verified policy used BCLM current-limit reads as policy input: at
startup, current limit below MAX selected `charging` and current limit at or
above MAX selected `sailing`; at runtime, current limit `> MAX` changed
`charging` to `sailing` and current limit `< MIN` changed `sailing` to
`charging`, with equality and interior values retaining state. This is
superseded history, not active truth.

Live failure evidence: sailing with pre-limit/target BCLM=77 and derived
capacity=62 stayed sailing; charging with pre-limit/target BCLM=83 and derived
capacity=84 stayed charging. With MIN=77 and MAX=83, these lower and upper
failures contradicted capacity-driven hysteresis and showed that BCLM must not
be the transition input.

The current successor uses derived usable charge capacity for startup and
runtime: capacity `< MAX` starts `charging`, otherwise it starts `sailing`;
while `charging`, capacity `>= MAX` sails; while `sailing`, capacity `< MIN`
charges. Equality at MIN and interior values retain state and target. The
current charging target is BCLM=MAX+1; sailing is BCLM=MIN-1. The current
implementation does not read the capacity file or `charge_full_design`; it
selects the first `type=Battery` directory and rereads `charge_now` and
`charge_full` on every sample. Charge inputs must be nonempty, single-line
decimal integers, with non-negative `charge_now`, positive `charge_full`, and
`charge_now <= charge_full`. BCLM is freshly read and validated each sample as
actuator/readback data; targets and verified readbacks remain retained, but BCLM
does not transition policy or repair drift. In that superseded intermediate
successor, Battery `status` was log-only; current status-driven governor
behavior is recorded above. First-Battery selection and strict charge derivation
guarantees remain unchanged.

Request-supplied runtime evidence recorded `charge_full_design=8790000`, learned
`charge_full=6829000`, `charge_now=5773000`, legacy `capacity=66`, and desired
output `capacity=84`. The current definition produces that output as integer
`100 * 5773000 / 6829000`, truncated toward zero; the design value and legacy
capacity value are not inputs. Derived capacity is the sole policy sensor; BCLM
actuates and reports the target/readback value.

### Superseded defensive architecture

Before the simplification, source inspection verified a defensive architecture
that:

- counted BCLM and usable-battery matches, rejected ambiguity, and resolved and
  deduplicated battery aliases;
- used strict decimal/one-line parsing for capacity and BCLM values;
- reopened and read back every BCLM write, and rediscovered interfaces while
  polling to repair external drift; and
- used signal request flags with main-path cleanup.

Those behaviors are retained as verified superseded history, not as active
runtime truth. The former defensive architecture was intentionally replaced
because auditability and simplicity outweigh exhaustive malformed or ambiguous
interface handling for this short linear daemon. The replacement uses
first-match discovery, direct validated reads with local integer branches,
retained paths in one loop, one `EXIT` cleanup function, and a readback from the
exact selected path after every control and cleanup write.

### Subprocess fixture transition

Current acceptance fixtures use ordinary temporary regular files for fake sysfs
values. The parent owns the daemon subprocess and drains its captured streams
with child-safe lifecycle handling; FIFO/writer protocol coordination is
superseded. Finite tests without external mutation retain the private zero-delay
seam. Regular-file transition tests use the production one-second delay where
parent-to-child timing needs it. Root override, finite poll limit, and
zero-delay inputs remain private subprocess inputs, not CLI, library, or
operator controls.

## 10. Maintenance

Update this file when verified implementation, interface, workflow, constraint,
validation, or failure behavior changes. Update `README.md` only for concise
operator setup or behavior changes. Reconcile any contract-dependent mismatch
through `SPEC.md` ownership before changing affected documentation.

Recheck target hardware, OpenRC runtime, logger receiver configuration,
installation, package source integrity, build output, and release evidence
before relying on a deployment. No monitoring cadence, backup procedure, upgrade
policy, or rollback workflow is implemented.

## 11. Agent rules

`AGENTS.md` owns onboarding, routing, edit boundaries, safety, and protected
surfaces. This file owns deeper `t2saild` implementation context. Never edit
`SPEC.md` during documentation synchronization. If verified implementation truth
conflicts with the contract, stop and report the exact mismatch and required
contract truth.

Do not run README snippets, execute services, operate hardware, perform remote
maintenance, or read, print, derive, move, or edit secrets. Preserve unrelated
working-tree changes. Keep unsupported behavior and unexecuted claims marked
`unknown`.

## 12. Current summary

Current source shape: a root-required foreground POSIX shell daemon accepts
positional MAX/MIN thresholds and an optional PROFILE/BATPROFILE pair, validates
them with quoted POSIX integer comparisons, selects the first BCLM and first
`type=Battery` entry, directly reads and validates current limit from the
readable/writable BCLM path using POSIX `case` digit-class matching and 0–100
range checks, and rereads non-negative `charge_now` and positive `charge_full`
each sample to derive truncated-toward-zero usable charge capacity. Invalid
reads or comparisons fail; no numeric normalization, sentinel, or fallback
occurs. At startup it selects charging below MAX or sailing at/above MAX from
capacity; at runtime it changes charging to sailing at or above MAX or sailing
to charging only below MIN. Charging targets physical BCLM=MAX+1; sailing
targets BCLM=MIN-1. BCLM is freshly read and validated each sample for
upper-charge actuator/readback reporting, but does not transition policy or
repair drift. Capacity is the sole state input. Control writes and handled-exit
BCLM=100 restoration use same-path readbacks; stable startup, verbose poll,
unconditional transition, and cleanup records report the outcomes. Startup and
each poll read selected-Battery `status` once; exact `Discharging` immediately
emits `state=discharging`, uses PROFILE for the first four consecutive samples,
and uses BATPROFILE from the fifth; every other nonempty one-line value resets
the count and immediately selects PROFILE. Status cannot affect capacity,
controller state, hysteresis, BCLM, writes, readbacks, or transition
`from`/`to`. Missing, unreadable, or empty status is fatal. CPU preflight
requires `cpupower`, validates available governor tokens, and validates the
current governor before initial BCLM control; after startup/poll records, each
mismatch emits exactly
`record=setprofile from=<CURRENT> target=<TARGET> streak=<0..5>` immediately
before the attempted command and reads back the selected governor. Equality
emits no record or command; quiet attempts still emit the record. Cleanup is
BCLM-only, so the final governor persists. Production `/sys` control requires
uid-0; the private fake-root subprocess seam canonicalizes its override with
POSIX shell operations before UID gating and bypasses that gate for tests only
when the canonical root is other than `/sys`. No external `realpath` utility is
required for canonicalization. Aliases canonicalizing to `/sys` remain
root-required before discovery. Validation remains before the root check,
discovery, and writes. OpenRC supplies 83/77 and performance/powersave defaults
and supervises the foreground process with logger routing; Makefile and package
metadata provide the three runtime files plus the cpupower dependency.

Static source and test-definition inspection is complete for the local daemon,
service, configuration, package, and documentation surfaces. Unverified: tests,
hardware and unplug response, installation, package/build/release output, OpenRC
lifecycle and directive support, logger delivery/persistence, target
compatibility, and abrupt-exit cleanup.
