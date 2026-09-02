# t2saild

`t2saild` is a root-required POSIX-shell daemon for an Apple T2 battery that
keeps your derived usable charge capacity within a configured window. Charging a
battery to 100% and keeping it there is bad for the capacity of the battery over
time. This daemon allows you to set a maximum charge limit to reduce battery
degradation. The ideal state for a battery is half charged / half discharged,
but for practicality 4/5 of the charge capacity gives the best of both worlds.

However, a fixed upper limit can cause repeated shallow charging after about 1%
of AC-connected drain, as the battery tends to very slowly lose charge, even
when connected to AC. This daemon doesn't just allow you to set a charge limit,
but it also allows you to avoid that repeated shallow cycling by introducing
`sailing` mode. So, you set an upper `MAX` and a lower `MIN` limit and the
daemon will charge to `>=MAX` and then "sail" to `<MIN` before charging again.

Another benefit is that `t2saild` allows you to automatically set power profiles
depending on your AC being connected or not. The default configuration puts your
Mac into performance mode by default, while being on power saving mode while not
connected to AC. Just remove the configuration to disable this feature.

## Requirements

- Linux on Apple T2 hardware with a usable battery and supported charge-limit
  interface
- OpenRC
- root access
- `findutils` and util-linux (`/usr/bin/logger`)
- `cpupower` in `PATH`, with the configured governors available

## Installation

From the checkout, install directly:

```sh
#

sudo make install

#
```

On Arch Linux, build and install the package instead:

```sh
#

makepkg -si

#
```

Installation does not enable or start the service.

## Getting Started

```
t2saild [-v|--verbose] [-V|--version] [-h|--help] MAX MIN [PROFILE BATPROFILE]
```

`MAX` is the upper threshold and `MIN` is the lower threshold. Both are
decimal-integer percentages satisfying exactly `20 <= MIN < MAX <= 99`. Options
must precede positional operands. `PROFILE` and `BATPROFILE` are optional only
as a pair; when omitted they default to `performance` and `powersave`. A lone
profile is invalid. Each supplied profile must be an exact token in the CPU
`scaling_available_governors` list. Configuration changes require a restart;
there is no configuration reload.

The daemon reads the selected Battery's one-line `status` once at startup and
once per poll. Exact `Discharging` is logged as `state=discharging` immediately;
`PROFILE` remains selected for its first four consecutive samples, and
`BATPROFILE` starts on the fifth and later. Every other nonempty one-line status
resets the count and immediately selects `PROFILE`. This is status-driven, not
AC detection. It reads the current governor before each selection; a mismatch
runs `cpupower frequency-set -g TARGET` and verifies the same governor path by
readback. An equal governor needs no command. Missing status or governor data,
an unavailable profile or `cpupower`, and command or readback failure stop the
daemon. The final selected governor remains in effect after exit; cleanup only
restores BCLM to `100`.

Verbose mode logs each poll. Every mode transition is logged, even without
verbose mode.

Direct invocation runs in the foreground and requires root for hardware control:

```sh
#

sudo /usr/bin/t2saild 83 77
sudo /usr/bin/t2saild --verbose 83 77

#
```

With OpenRC, configure `/etc/conf.d/t2saild`, then enable and start it
explicitly. The shipped defaults are logical `MAX=83` and `MIN=77`; charging
uses physical BCLM target `84` (`MAX+1`), while sailing uses physical BCLM
target `76` (`MIN-1`).

```conf
t2saild_min=77
t2saild_max=83
t2saild_profile=performance
t2saild_batprofile=powersave
t2saild_args=""
```

`t2saild_args` passes optional daemon flags before positional operands in the
order `MAX`, `MIN`, `PROFILE`, `BATPROFILE`. Leave it empty for no optional
flags. For verbose polling, use `t2saild_args="--verbose"`; OpenRC then invokes
`t2saild --verbose MAX MIN PROFILE BATPROFILE`.

```sh
#

sudo rc-update add t2saild default
sudo rc-service t2saild start

#
```

## Topping up / Shutdown

Stopping while AC remains connected can let the battery top up toward 100.
Remove AC before shutdown unless topping up while powered off is intended.

A handled shutdown attempts to restore the charge limit to 100. Cleanup failure,
power loss, or `SIGKILL` can leave the last limit in place.
