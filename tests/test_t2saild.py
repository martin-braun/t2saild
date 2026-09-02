import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "t2saild"


class FakeSysfs(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "devices/chip").mkdir(parents=True)
        self.limit = self.root / "devices/chip/battery_charge_limit"
        self.battery = self.root / "class/power_supply/BAT0"
        self.status = self.battery / "status"
        self.cpufreq = self.root / "devices/system/cpu/cpu0/cpufreq"
        self.cpupower_bin = self.root / "bin"
        self.utility_bin = self.root / "utility-bin"
        self.cpupower_log = self.root / "cpupower.log"
        self.cat_log = self.root / "cat.log"
        self.battery.mkdir(parents=True)
        self.cpufreq.mkdir(parents=True)
        self.cpupower_bin.mkdir()
        self.utility_bin.mkdir()
        for utility in ("cat", "find", "id", "sh"):
            utility_path = next(
                Path(directory) / utility
                for directory in os.get_exec_path()
                if (Path(directory) / utility).is_file()
            )
            if utility == "cat":
                self.write(
                    self.utility_bin / utility,
                    "#!/bin/sh\n"
                    'printf \'%s\\n\' "$1" >> "$T2SAILD_TEST_CAT_LOG"\n'
                    f'exec "{utility_path}" "$@"\n',
                )
                os.chmod(self.utility_bin / utility, 0o755)
            else:
                os.symlink(utility_path, self.utility_bin / utility)
        self.write(self.limit, "80\n")
        self.write(self.battery / "type", "Battery\n")
        self.write(self.battery / "charge_now", "5773000\n")
        self.write(self.battery / "charge_full", "6829000\n")
        self.write(self.status, "Charging\n")
        self.write(
            self.cpufreq / "scaling_available_governors",
            "performance powersave\n",
        )
        self.write(self.cpufreq / "scaling_governor", "performance\n")
        self.cpupower = self.cpupower_bin / "cpupower"
        self.write(
            self.cpupower,
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$T2SAILD_TEST_CPUPOWER_LOG"\n'
            "printf 'fake-cpupower %s\\n' \"$*\"\n"
            'if [ "$T2SAILD_TEST_CPUPOWER_MODE" = fail ]; then exit 1; fi\n'
            'if [ "$T2SAILD_TEST_CPUPOWER_MODE" = mismatch ]; then\n'
            "  printf '%s\\n' performance > \"$T2SAILD_TEST_GOVERNOR\"\n"
            "else\n"
            '  printf \'%s\\n\' "$3" > "$T2SAILD_TEST_GOVERNOR"\n'
            "fi\n",
        )
        os.chmod(self.cpupower, 0o755)

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(value)

    def write_charge(self, now, full):
        self.write(self.battery / "charge_now", f"{now}\n")
        self.write(self.battery / "charge_full", f"{full}\n")

    def write_status(self, value):
        self.write(self.status, value)

    def governor_calls(self):
        if not self.cpupower_log.exists():
            return []
        return self.cpupower_log.read_text().splitlines()

    def cat_calls(self, path):
        if not self.cat_log.exists():
            return []
        return [
            line
            for line in self.cat_log.read_text().splitlines()
            if line == str(path)
        ]

    def run_daemon(
        self,
        minimum=77,
        maximum=83,
        polls=1,
        verbose=False,
        zero_delay=True,
        profile=None,
        batprofile=None,
        cpu_mode=None,
        path_only=False,
    ):
        environment = os.environ.copy()
        environment["T2SAILD_ROOT"] = str(self.root)
        environment["T2SAILD_POLL_LIMIT"] = str(polls)
        environment["T2SAILD_NO_DELAY"] = "1" if zero_delay else "0"
        environment["PATH"] = (
            f"{self.cpupower_bin}{os.pathsep}{self.utility_bin}"
            if path_only
            else f"{self.cpupower_bin}{os.pathsep}{self.utility_bin}{os.pathsep}{environment['PATH']}"
        )
        environment["T2SAILD_TEST_CPUPOWER_LOG"] = str(self.cpupower_log)
        environment["T2SAILD_TEST_CAT_LOG"] = str(self.cat_log)
        environment["T2SAILD_TEST_GOVERNOR"] = str(
            self.cpufreq / "scaling_governor"
        )
        if cpu_mode is not None:
            environment["T2SAILD_TEST_CPUPOWER_MODE"] = cpu_mode
        if verbose:
            arguments = ("--verbose", str(maximum), str(minimum))
        else:
            arguments = (str(maximum), str(minimum))
        if profile is not None:
            arguments += (profile, batprofile)
        return subprocess.run(
            [str(SOURCE), *arguments],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

    def start_daemon(
        self,
        minimum=77,
        maximum=83,
        polls=4,
        verbose=False,
        zero_delay=False,
        profile=None,
        batprofile=None,
        cpu_mode=None,
        path_only=False,
    ):
        environment = os.environ.copy()
        environment["T2SAILD_ROOT"] = str(self.root)
        environment["T2SAILD_POLL_LIMIT"] = str(polls)
        environment["T2SAILD_NO_DELAY"] = "1" if zero_delay else "0"
        environment["PATH"] = (
            f"{self.cpupower_bin}{os.pathsep}{self.utility_bin}"
            if path_only
            else f"{self.cpupower_bin}{os.pathsep}{self.utility_bin}{os.pathsep}{environment['PATH']}"
        )
        environment["T2SAILD_TEST_CPUPOWER_LOG"] = str(self.cpupower_log)
        environment["T2SAILD_TEST_CAT_LOG"] = str(self.cat_log)
        environment["T2SAILD_TEST_GOVERNOR"] = str(
            self.cpufreq / "scaling_governor"
        )
        if cpu_mode is not None:
            environment["T2SAILD_TEST_CPUPOWER_MODE"] = cpu_mode
        arguments = [str(SOURCE)]
        if verbose:
            arguments.append("--verbose")
        arguments.extend((str(maximum), str(minimum)))
        if profile is not None:
            arguments.extend((profile, batprofile))
        process = subprocess.Popen(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        self.addCleanup(self.reap_daemon, process)
        return process

    @staticmethod
    def reap_daemon(process):
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        finally:
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def assert_clean_exit(self, result):
        self.assertEqual(0, result.returncode)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertIn("record=cleanup target=100 limit=100", result.stdout)


class CliTests(FakeSysfs):
    def run_cli(self, *args):
        environment = os.environ.copy()
        environment["T2SAILD_ROOT"] = str(self.root)
        environment["T2SAILD_POLL_LIMIT"] = "1"
        environment["T2SAILD_NO_DELAY"] = "1"
        environment["PATH"] = (
            f"{self.cpupower_bin}{os.pathsep}{environment['PATH']}"
        )
        environment["T2SAILD_TEST_CPUPOWER_LOG"] = str(self.cpupower_log)
        environment["T2SAILD_TEST_CAT_LOG"] = str(self.cat_log)
        environment["T2SAILD_TEST_GOVERNOR"] = str(
            self.cpufreq / "scaling_governor"
        )
        return subprocess.run(
            [str(SOURCE), *args],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

    def test_help_and_version_need_no_root_or_sysfs(self):
        help_result = self.run_cli("--help")
        self.assertEqual(0, help_result.returncode)
        self.assertEqual(
            "Usage: t2saild [-v|--verbose] [-V|--version] [-h|--help] MAX MIN "
            "[PROFILE BATPROFILE]\n"
            "\n"
            "Maintain battery charge between MIN and MAX.\n"
            "\n"
            "  -v, --verbose   Print record=poll min=<MIN> max=<MAX> limit=<LIMIT> "
            "target=<TARGET> capacity=<CAPACITY> state=<STATE> on each poll.\n"
            "  -V, --version   Print the version.\n"
            "  -h, --help      Print this help.\n",
            help_result.stdout,
        )
        short_help_result = self.run_cli("-h")
        self.assertEqual(0, short_help_result.returncode)
        self.assertEqual(help_result.stdout, short_help_result.stdout)
        self.assertNotIn("reduce battery wear", help_result.stdout)
        for option in ("-V", "--version"):
            with self.subTest(option=option):
                version_result = self.run_cli(option)
                self.assertEqual(0, version_result.returncode)
                self.assertEqual("t2saild 0.1.0\n", version_result.stdout)

    def test_options_are_accepted_only_before_operands(self):
        for option in ("-v", "--verbose"):
            self.write(self.limit, "80\n")
            self.write_charge(3414500, 6829000)
            result = self.run_cli(option, "83", "77")
            self.assertEqual(0, result.returncode)
            self.assertIn(
                "record=poll min=77 max=83 limit=84 target=84 capacity=50 "
                "state=charging",
                result.stdout,
            )
        for args in (("77", "--verbose"), ("77", "--help"), ("77", "-V")):
            with self.subTest(args=args):
                self.assertNotEqual(0, self.run_cli(*args).returncode)

    def test_unknown_missing_extra_and_named_options_fail(self):
        for args in (
            ("--unknown", "77", "83"),
            ("--low-threshold", "77", "83"),
            ("77",),
            ("77", "83", "90"),
            ("83", "77", "performance", "powersave", "extra"),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(0, self.run_cli(*args).returncode)

    def test_threshold_bounds_and_text_fail_before_control(self):
        for maximum, minimum in (
            ("19", "83"),
            ("20", "20"),
            ("77", "83"),
            ("100", "20"),
            ("101", "20"),
            ("83.0", "20"),
            ("", "20"),
        ):
            with self.subTest(minimum=minimum, maximum=maximum):
                result = self.run_cli(maximum, minimum)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("20 <= MIN < MAX <= 99", result.stderr)

    def test_threshold_order_defaults_and_explicit_profiles(self):
        default_result = self.run_cli("83", "77")
        explicit_result = self.run_cli("83", "77", "performance", "powersave")
        self.assertEqual(0, default_result.returncode)
        self.assertEqual(0, explicit_result.returncode)
        self.assertEqual(default_result.stdout, explicit_result.stdout)
        for args in (("83",), ("83", "77", "performance")):
            with self.subTest(args=args):
                self.assertNotEqual(0, self.run_cli(*args).returncode)


class StartupAndStateTests(FakeSysfs):
    def test_discharging_status_logs_immediately_before_profile_debounce(self):
        for limit, now, capacity, state in (
            (80, 3414500, 50, "charging"),
            (83, 5773000, 84, "sailing"),
        ):
            with self.subTest(state=state):
                self.write(self.limit, f"{limit}\n")
                self.write_charge(now, 6829000)
                self.write_status("Discharging\n")
                self.write(self.cpufreq / "scaling_governor", "performance\n")
                if self.cpupower_log.exists():
                    self.cpupower_log.unlink()
                result = self.run_daemon(verbose=True)
                self.assert_clean_exit(result)
                self.assertIn(
                    f"record=startup min=77 max=83 limit={'84' if state == 'charging' else '76'} "
                    f"target={'84' if state == 'charging' else '76'} capacity={capacity} "
                    "state=discharging",
                    result.stdout,
                )
                self.assertIn("state=discharging", result.stdout)
                self.assertEqual([], self.governor_calls())

    def test_discharging_debounce_counts_startup_and_saturates_at_five(self):
        self.write_charge(3414500, 6829000)
        self.write_status("Discharging\n")
        result = self.run_daemon(polls=7, verbose=True)
        records = [
            line
            for line in result.stdout.splitlines()
            if line.startswith(("record=startup", "record=poll"))
        ]
        self.assertEqual(8, len(records))
        self.assertTrue(all("state=discharging" in line for line in records))
        self.assertEqual(["frequency-set -g powersave"], self.governor_calls())
        self.assertEqual(
            1,
            result.stdout.count(
                "record=setprofile from=performance target=powersave streak=5"
            ),
        )
        self.assertEqual(
            1, result.stdout.count("fake-cpupower frequency-set -g powersave")
        )

    def test_non_discharging_status_resets_and_restores_profile(self):
        self.write_charge(3414500, 6829000)
        self.write_status("Discharging\n")
        process = self.start_daemon(polls=9, verbose=True)
        self.assertIn("record=startup", process.stdout.readline())
        for _ in range(3):
            self.assertIn("record=poll", process.stdout.readline())
        self.assertIn("state=discharging", process.stdout.readline())
        self.assertEqual(
            "record=setprofile from=performance target=powersave streak=5\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "fake-cpupower frequency-set -g powersave\n",
            process.stdout.readline(),
        )
        self.write_status("Charging\n")
        restored_poll = process.stdout.readline()
        self.assertEqual(
            "record=setprofile from=powersave target=performance streak=0\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "fake-cpupower frequency-set -g performance\n",
            process.stdout.readline(),
        )
        self.write_status("Discharging\n")
        later_polls = [process.stdout.readline() for _ in range(4)]
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn("record=poll", restored_poll)
        self.assertIn("state=charging", restored_poll)
        self.assertTrue(
            all(
                "record=poll" in line and "state=discharging" in line
                for line in later_polls
            )
        )
        self.assertEqual(
            ["frequency-set -g powersave", "frequency-set -g performance"],
            self.governor_calls(),
        )
        self.assertNotIn("record=setprofile", "".join(later_polls) + stdout)

    def test_other_nonempty_statuses_select_regular_profile(self):
        for value in (
            "Charging\n",
            "not-a-status\n",
            "discharging\n",
            "Discharging \n",
        ):
            with self.subTest(value=value):
                self.write(self.limit, "83\n")
                self.write_status(value)
                result = self.run_daemon(verbose=True)
                self.assert_clean_exit(result)
                self.assertIn("state=sailing", result.stdout)
                self.assertNotIn("state=discharging", result.stdout)
                self.assertEqual([], self.governor_calls())
                self.assertNotIn("record=setprofile", result.stdout)

    def test_missing_or_empty_status_fails_after_bclm_control(self):
        for unreadable in (False, True):
            with self.subTest(unreadable=unreadable):
                self.write(self.limit, "83\n")
                if unreadable:
                    self.write_status("Discharging\n")
                    self.status.unlink()
                    self.status.mkdir()
                else:
                    self.status.unlink()
                if not unreadable:
                    self.write_status("")
                result = self.run_daemon(verbose=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("status", result.stderr)
                self.assertEqual("100\n", self.limit.read_text())
                self.assertIn(
                    "record=cleanup target=100 limit=100", result.stdout
                )
                self.assertEqual([], self.governor_calls())

    def test_status_changes_are_reread_without_transition_or_control(self):
        self.write(self.limit, "83\n")
        process = self.start_daemon(polls=4, verbose=True)
        self.assertIn("state=sailing", process.stdout.readline())
        self.assertIn("state=sailing", process.stdout.readline())
        limit_mtime = self.limit.stat().st_mtime_ns
        self.write_status("Discharging\n")
        self.assertIn("state=discharging", process.stdout.readline())
        self.assertEqual("76\n", self.limit.read_text())
        self.assertEqual(limit_mtime, self.limit.stat().st_mtime_ns)
        self.write_status("Charging\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn("state=sailing", stdout)
        self.assertNotIn("record=transition", stdout)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertEqual([], self.governor_calls())

    def test_status_is_read_once_for_startup_and_each_poll(self):
        result = self.run_daemon(polls=3, verbose=True)
        self.assert_clean_exit(result)
        self.assertEqual(4, len(self.cat_calls(self.status)))

    def test_explicit_profiles_select_regular_and_discharging_governors(self):
        self.write_status("Charging\n")
        result = self.run_daemon(profile="powersave", batprofile="performance")
        self.assert_clean_exit(result)
        self.assertEqual(["frequency-set -g powersave"], self.governor_calls())

        self.write(self.limit, "83\n")
        self.write_status("Discharging\n")
        result = self.run_daemon(profile="powersave", batprofile="performance")
        self.assert_clean_exit(result)
        self.assertEqual(["frequency-set -g powersave"], self.governor_calls())

        self.write(self.limit, "80\n")
        self.write_charge(3414500, 6829000)
        result = self.run_daemon(
            polls=4, profile="powersave", batprofile="performance"
        )
        self.assert_clean_exit(result)
        self.assertEqual(
            ["frequency-set -g powersave", "frequency-set -g performance"],
            self.governor_calls(),
        )

        self.write(self.limit, "80\n")
        result = self.run_daemon(
            profile="performancefoo", batprofile="powersave"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("profile", result.stderr)
        self.assertEqual("80\n", self.limit.read_text())

    def test_governor_equality_skips_command_on_quiet_polls(self):
        result = self.run_daemon(polls=3, verbose=False)
        self.assert_clean_exit(result)
        self.assertEqual([], self.governor_calls())
        self.assertNotIn("record=setprofile", result.stdout)

    def test_setprofile_startup_is_unconditional_and_ordered_before_command(
        self,
    ):
        self.write_charge(3414500, 6829000)
        self.write(self.cpufreq / "scaling_governor", "powersave\n")
        result = self.run_daemon(verbose=False)
        self.assert_clean_exit(result)
        lines = result.stdout.splitlines()
        self.assertEqual(
            [
                "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
                "state=charging",
                "record=setprofile from=powersave target=performance streak=0",
                "fake-cpupower frequency-set -g performance",
            ],
            lines[:3],
        )
        self.assertNotIn("record=poll", result.stdout)

    def test_quiet_poll_mismatch_emits_setprofile_without_poll(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=2, verbose=False)
        self.assertIn("record=startup", process.stdout.readline())
        self.write(self.cpufreq / "scaling_governor", "powersave\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn(
            "record=setprofile from=powersave target=performance streak=0",
            stdout,
        )
        self.assertIn("fake-cpupower frequency-set -g performance", stdout)
        self.assertNotIn("record=poll", stdout)

    def test_setprofile_repairs_fourth_and_switches_once_on_fifth(self):
        self.write_charge(3414500, 6829000)
        self.write_status("Discharging\n")
        governor_reads = self.root / "governor-reads"
        cat = self.utility_bin / "cat"
        cat_script = cat.read_text()
        self.write(
            cat,
            cat_script.replace(
                "exec ",
                f"""case "$1" in
  *scaling_governor)
  reads=0
  if [ -f "{governor_reads}" ]; then
    IFS= read -r reads < "{governor_reads}"
  fi
  reads=$((reads + 1))
  printf '%s\\n' "$reads" > "{governor_reads}"
  if [ "$reads" -eq 5 ]; then
    printf 'powersave\\n' > "$1"
  fi
  ;;
esac
exec """,
                1,
            ),
        )
        process = self.start_daemon(polls=5, verbose=True)
        startup = process.stdout.readline()
        first_poll = process.stdout.readline()
        second_poll = process.stdout.readline()
        self.assertIn("record=startup", startup)
        self.assertIn("state=discharging", startup)
        self.assertIn("record=poll", first_poll)
        self.assertIn("state=discharging", first_poll)
        self.assertIn("record=poll", second_poll)
        self.assertIn("state=discharging", second_poll)
        self.assertEqual([], self.governor_calls())

        fourth_poll = process.stdout.readline()
        self.assertIn("record=poll", fourth_poll)
        self.assertEqual(
            "record=setprofile from=powersave target=performance streak=4\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "fake-cpupower frequency-set -g performance\n",
            process.stdout.readline(),
        )

        fifth_poll = process.stdout.readline()
        self.assertIn("record=poll", fifth_poll)
        self.assertEqual(
            "record=setprofile from=performance target=powersave streak=5\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "fake-cpupower frequency-set -g powersave\n",
            process.stdout.readline(),
        )
        later_poll = process.stdout.readline()
        self.assertIn("record=poll", later_poll)
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertEqual(
            [
                "frequency-set -g performance",
                "frequency-set -g powersave",
            ],
            self.governor_calls(),
        )
        self.assertNotIn("record=setprofile", later_poll + stdout)

    def test_governor_dependencies_fail_before_initial_bclm_write(self):
        for setup in (
            lambda: self.cpupower.unlink(),
            lambda: (self.cpufreq / "scaling_available_governors").unlink(),
            lambda: self.write(
                self.cpufreq / "scaling_available_governors", ""
            ),
            lambda: self.write(
                self.cpufreq / "scaling_available_governors",
                "performance\npowersave\n",
            ),
            lambda: self.write(self.cpufreq / "scaling_governor", ""),
            lambda: (self.cpufreq / "scaling_governor").unlink(),
            lambda: self.write(
                self.cpufreq / "scaling_governor", "performance\npowersave\n"
            ),
        ):
            with self.subTest(setup=setup):
                setup()
                result = self.run_daemon(path_only=True)
                self.assertNotEqual(0, result.returncode)
                self.assertTrue(
                    "governor" in result.stderr or "cpupower" in result.stderr
                )
                self.assertEqual("80\n", self.limit.read_text())
                if not self.cpupower.exists():
                    self.write(
                        self.cpupower,
                        '#!/bin/sh\nprintf \'%s\\n\' "$3" > "$T2SAILD_TEST_GOVERNOR"\n',
                    )
                    os.chmod(self.cpupower, 0o755)
                self.write(
                    self.cpufreq / "scaling_available_governors",
                    "performance powersave\n",
                )
                self.write(self.cpufreq / "scaling_governor", "performance\n")

    def test_governor_command_and_readback_fail_after_control_cleanup(self):
        for mode in ("fail", "mismatch"):
            with self.subTest(mode=mode):
                self.write(self.limit, "80\n")
                self.write_status("Discharging\n")
                process = self.start_daemon(
                    polls=5, verbose=True, cpu_mode=mode
                )
                self.assertIn("record=startup", process.stdout.readline())
                stdout, stderr = process.communicate(timeout=8)
                self.assertNotEqual(0, process.returncode)
                self.assertEqual("100\n", self.limit.read_text())
                self.assertIn("governor", stderr)
                self.assertIn("record=cleanup target=100 limit=100", stdout)
                self.assertEqual(
                    1,
                    stdout.count(
                        "record=setprofile from=performance target=powersave "
                        "streak=5"
                    ),
                )
                self.assertIn(
                    "record=setprofile from=performance target=powersave streak=5\n"
                    "fake-cpupower frequency-set -g powersave",
                    stdout,
                )

    def test_startup_governor_command_failure_restores_bclm(self):
        self.write_status("Discharging\n")
        self.write(self.cpufreq / "scaling_governor", "powersave\n")
        result = self.run_daemon(cpu_mode="fail")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertIn("governor command failed", result.stderr)
        self.assertIn("record=cleanup target=100 limit=100", result.stdout)
        self.assertIn(
            "record=setprofile from=powersave target=performance streak=1\n"
            "fake-cpupower frequency-set -g performance",
            result.stdout,
        )

    def test_governor_readback_is_checked_each_poll(self):
        self.write(self.limit, "83\n")
        process = self.start_daemon(polls=3, verbose=True)
        process.stdout.readline()
        process.stdout.readline()
        self.write(self.cpufreq / "scaling_governor", "not a governor\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode)
        self.assertIn("invalid current governor", stderr)
        self.assertNotIn("record=setprofile", stdout)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertIn("record=cleanup target=100 limit=100", stdout)

    def test_startup_uses_fresh_capacity_for_state_and_target(self):
        for limit, now, full, capacity, state, target in (
            (80, 3414500, 6829000, 50, "charging", 84),
            (83, 3414500, 6829000, 50, "charging", 84),
            (80, 5668070, 6829000, 83, "sailing", 76),
            (83, 5773000, 6829000, 84, "sailing", 76),
        ):
            with self.subTest(limit=limit, capacity=capacity):
                self.write(self.limit, f"{limit}\n")
                self.write_charge(now, full)
                result = self.run_daemon()
                self.assert_clean_exit(result)
                self.assertIn(
                    f"record=startup min=77 max=83 limit={target} "
                    f"target={target} capacity={capacity} state={state}",
                    result.stdout,
                )

    def test_startup_at_max_sails_and_runtime_at_min_remains_sailing(self):
        self.write(self.limit, "83\n")
        result = self.run_daemon(verbose=True)
        self.assert_clean_exit(result)
        self.assertIn(
            "record=startup min=77 max=83 limit=76 target=76 capacity=84 "
            "state=sailing",
            result.stdout,
        )
        self.assertIn(
            "record=poll min=77 max=83 limit=76 target=76 capacity=84 "
            "state=sailing",
            result.stdout,
        )

    def test_charging_maximum_99_uses_bclm_target_100(self):
        self.write_charge(3414500, 6829000)
        result = self.run_daemon(minimum=20, maximum=99)
        self.assert_clean_exit(result)
        self.assertIn(
            "record=startup min=20 max=99 limit=100 target=100 capacity=50 "
            "state=charging",
            result.stdout,
        )

    def test_charging_above_max_transitions_to_sailing(self):
        self.write(self.limit, "80\n")
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4, verbose=True)
        startup = process.stdout.readline()
        first_poll = process.stdout.readline()
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            startup,
        )
        self.assertEqual(
            "record=poll min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            first_poll,
        )
        self.write_charge(5773000, 6829000)
        transition = process.stdout.readline()
        sailing_poll = process.stdout.readline()
        self.assertIn(
            "record=transition from=charging to=sailing min=77 max=83 "
            "pre_limit=84 target=76 post_limit=76 capacity=84 state=sailing",
            transition,
        )
        self.assertIn("state=sailing", sailing_poll)
        self.write(self.limit, "100\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertNotIn("from=sailing to=charging", stdout)
        self.assertNotIn("from=sailing to=charging", sailing_poll)
        self.assertNotIn("from=sailing to=charging", transition)
        self.assertEqual("100\n", self.limit.read_text())

    def test_capacity_equality_and_interior_retain_state_and_target(self):
        self.write(self.limit, "80\n")
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=6, verbose=True)
        self.assertIn("capacity=50 state=charging", process.stdout.readline())
        self.assertIn("capacity=50 state=charging", process.stdout.readline())

        self.write_charge(5668070, 6829000)
        self.assertIn("from=charging to=sailing", process.stdout.readline())
        self.assertIn("capacity=83 state=sailing", process.stdout.readline())
        self.write_charge(5599780, 6829000)
        self.assertIn("capacity=82 state=sailing", process.stdout.readline())

        self.write_charge(5258330, 6829000)
        self.assertIn(
            "limit=76 target=76 capacity=77 state=sailing",
            process.stdout.readline(),
        )
        self.write_charge(5190040, 6829000)
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn("from=sailing to=charging", stdout)
        self.assertIn("capacity=76 state=charging", stdout)
        self.assertEqual("100\n", self.limit.read_text())

    def test_bclm_changes_alone_do_not_transition_or_repair(self):
        self.write(self.limit, "80\n")
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4, verbose=True)
        process.stdout.readline()
        process.stdout.readline()
        self.write(self.limit, "77\n")
        changed_poll = process.stdout.readline()
        self.assertIn(
            "record=poll min=77 max=83 limit=77 target=84 capacity=50 state=charging",
            changed_poll,
        )
        self.assertEqual("77\n", self.limit.read_text())
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertNotIn("record=transition", changed_poll + stdout)
        self.assertNotIn("record=transition", stdout)
        self.assertEqual("100\n", self.limit.read_text())

    def test_transition_record_is_unconditional(self):
        self.write(self.limit, "80\n")
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4)
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.write_charge(5773000, 6829000)
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn(
            "record=transition from=charging to=sailing min=77 max=83 "
            "pre_limit=84 target=76 post_limit=76 capacity=84 state=sailing",
            stdout,
        )
        self.assertNotIn("record=poll", stdout)
        self.assertEqual("100\n", self.limit.read_text())

    def test_sailing_below_min_transitions_to_charging(self):
        self.write(self.limit, "83\n")
        self.write_charge(5773000, 6829000)
        process = self.start_daemon(polls=4, verbose=True)
        startup = process.stdout.readline()
        first_poll = process.stdout.readline()
        self.assertEqual(
            "record=startup min=77 max=83 limit=76 target=76 capacity=84 "
            "state=sailing\n",
            startup,
        )
        self.assertEqual(
            "record=poll min=77 max=83 limit=76 target=76 capacity=84 "
            "state=sailing\n",
            first_poll,
        )
        self.write(self.limit, "77\n")
        self.write_charge(4233980, 6829000)
        transition = process.stdout.readline()
        charging_poll = process.stdout.readline()
        self.assertIn(
            "record=transition from=sailing to=charging min=77 max=83 "
            "pre_limit=77 target=84 post_limit=84 capacity=62 state=charging",
            transition,
        )
        self.assertIn("state=charging", charging_poll)
        self.write(self.limit, "70\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertNotIn("from=charging to=sailing", stdout)
        self.assertNotIn("from=charging to=sailing", charging_poll)
        self.assertNotIn("from=charging to=sailing", transition)
        self.assertEqual("100\n", self.limit.read_text())

    def test_transition_controller_states_are_preserved_with_discharging_output(
        self,
    ):
        for initial_limit, changed_limit, from_state, to_state, target in (
            (80, 83, "charging", "sailing", 76),
            (83, 77, "sailing", "charging", 84),
        ):
            with self.subTest(from_state=from_state):
                self.write(self.cpufreq / "scaling_governor", "performance\n")
                self.write(self.limit, f"{initial_limit}\n")
                self.write_charge(
                    3414500 if from_state == "charging" else 5773000,
                    6829000,
                )
                self.write_status("Discharging\n")
                process = self.start_daemon(polls=4, verbose=True)
                startup = process.stdout.readline()
                self.assertIn("record=startup", startup)
                self.assertIn("state=discharging", startup)
                first_poll = process.stdout.readline()
                self.assertIn("record=poll", first_poll)
                self.assertIn("state=discharging", first_poll)
                self.write(self.limit, f"{changed_limit}\n")
                self.write_charge(
                    5773000 if from_state == "charging" else 4233980,
                    6829000,
                )
                transition = process.stdout.readline()
                stdout, stderr = process.communicate(timeout=8)
                self.assertEqual(0, process.returncode, stderr)
                self.assertIn(
                    f"record=transition from={from_state} to={to_state} "
                    f"min=77 max=83 pre_limit={changed_limit} target={target} "
                    f"post_limit={target} capacity="
                    f"{84 if from_state == 'charging' else 62} state=discharging",
                    transition,
                )
                self.assertIn("state=discharging", stdout)
                self.assertIn("record=poll", stdout)
                self.assertIn(
                    "record=setprofile from=performance target=powersave streak=5\n"
                    "fake-cpupower frequency-set -g powersave",
                    stdout,
                )

    def test_sailing_remains_sailing_at_minimum(self):
        for (
            minimum,
            maximum,
            startup_limit,
            startup_charge,
            boundary_charge,
            startup_capacity,
        ) in (
            (77, 83, 83, (5773000, 6829000), (5258330, 6829000), 84),
            (20, 99, 99, (6829000, 6829000), (1365800, 6829000), 100),
        ):
            with self.subTest(minimum=minimum, maximum=maximum):
                self.write(self.limit, f"{startup_limit}\n")
                self.write_charge(*startup_charge)
                process = self.start_daemon(
                    minimum=minimum,
                    maximum=maximum,
                    polls=4,
                    verbose=True,
                )
                startup = process.stdout.readline()
                first_poll = process.stdout.readline()
                self.assertEqual(
                    f"record=startup min={minimum} max={maximum} limit={minimum - 1} "
                    f"target={minimum - 1} capacity={startup_capacity} state=sailing\n",
                    startup,
                )
                self.assertEqual(
                    f"record=poll min={minimum} max={maximum} limit={minimum - 1} "
                    f"target={minimum - 1} capacity={startup_capacity} state=sailing\n",
                    first_poll,
                )
                self.write_charge(*boundary_charge)
                stdout, stderr = process.communicate(timeout=8)
                self.assertEqual(0, process.returncode, stderr)
                later_polls = [
                    line
                    for line in stdout.splitlines()
                    if line.startswith("record=poll")
                    and f"limit={minimum - 1}" in line
                ]
                self.assertTrue(later_polls)
                self.assertTrue(
                    all(line.endswith("state=sailing") for line in later_polls)
                )
                self.assertEqual("100\n", self.limit.read_text())

    def test_charge_samples_are_reread_each_poll(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=3, verbose=True)
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "record=poll min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.write(self.battery / "charge_now", "4233980\n")
        self.assertEqual(
            "record=poll min=77 max=83 limit=84 target=84 capacity=62 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.write(self.battery / "charge_now", "3414500\n")
        self.write(self.battery / "charge_full", "11546000\n")
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(0, process.returncode, stderr)
        self.assertIn(
            "record=poll min=77 max=83 limit=84 target=84 capacity=29 "
            "state=charging",
            stdout,
        )
        self.assertNotIn("record=transition", stdout)
        self.assertEqual("100\n", self.limit.read_text())

    def test_capacity_file_is_ignored(self):
        result = self.run_daemon()
        self.assert_clean_exit(result)
        self.assertIn("capacity=84", result.stdout)

        for value in ("not-a-capacity\n", "101\n", "-1\n"):
            with self.subTest(value=value):
                self.write(self.limit, "80\n")
                self.write(self.battery / "capacity", value)
                self.write(
                    self.battery / "charge_full_design", "not-a-health-value\n"
                )
                result = self.run_daemon()
                self.assert_clean_exit(result)
                self.assertIn("capacity=84", result.stdout)


class DiscoveryAndIoTests(FakeSysfs):
    def test_first_match_bclm_and_battery_is_used(self):
        second_limit = self.root / "devices/aaa/battery_charge_limit"
        second_limit.parent.mkdir()
        self.write(second_limit, "55\n")
        second_battery = self.root / "class/power_supply/BAT1"
        second_battery.mkdir()
        self.write(second_battery / "type", "Battery\n")
        self.write(second_battery / "charge_now", "9000000\n")
        self.write(second_battery / "charge_full", "10000000\n")
        result = self.run_daemon()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            (self.limit.read_text(), second_limit.read_text()),
            (("100\n", "55\n"), ("80\n", "100\n")),
        )
        self.assertIn(
            "record=startup min=77 max=83 limit=76 target=76 "
            "capacity=84 state=sailing",
            result.stdout,
        )

    def test_missing_bclm_or_battery_fails_cleanly(self):
        self.limit.unlink()
        result = self.run_daemon()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("battery_charge_limit", result.stderr)

        self.write(self.limit, "80\n")
        self.battery.rename(self.root / "class/power_supply/AC")
        self.write(self.root / "class/power_supply/AC/type", "Mains\n")
        result = self.run_daemon()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("type=Battery", result.stderr)
        self.assertEqual("80\n", self.limit.read_text())

    def test_missing_charge_input_fails_before_control(self):
        for name in ("charge_now", "charge_full"):
            with self.subTest(name=name):
                self.write_charge(5773000, 6829000)
                (self.battery / name).unlink()
                result = self.run_daemon()
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("80\n", self.limit.read_text())

    def test_invalid_charge_values_fail_before_control(self):
        values = (
            ("", "6829000\n"),
            ("not-a-number\n", "6829000\n"),
            ("1.0\n", "6829000\n"),
            ("1\n2\n", "6829000\n"),
            ("-1\n", "6829000\n"),
            ("5773000\n", ""),
            ("5773000\n", "not-a-number\n"),
            ("5773000\n", "1.0\n"),
            ("5773000\n", "1\n2\n"),
            ("5773000\n", "-1\n"),
            ("5773000\n", "0\n"),
            ("6829001\n", "6829000\n"),
        )
        for now, full in values:
            with self.subTest(now=now, full=full):
                self.write(self.battery / "charge_now", now)
                self.write(self.battery / "charge_full", full)
                result = self.run_daemon()
                self.assertNotEqual(0, result.returncode)
                self.assertIn("capacity", result.stderr)
                self.assertEqual("80\n", self.limit.read_text())

    def test_invalid_current_limit_fails_before_control(self):
        for value in ("", "not-a-number\n", "1.0\n", "1\n2\n", "-1\n", "101\n"):
            with self.subTest(value=value):
                self.write(self.limit, value)
                result = self.run_daemon()
                self.assertNotEqual(0, result.returncode)
                self.assertIn("current limit", result.stderr)
                self.assertEqual(value, self.limit.read_text())
                self.write(self.limit, "80\n")

    def test_unreadable_current_limit_fails_without_cleanup_ownership(self):
        self.limit.unlink()
        self.limit.mkdir()
        result = self.run_daemon()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("cannot read current limit", result.stderr)
        self.assertNotIn("cleanup", result.stderr)

    def test_capacity_read_failure_after_control_restores_limit(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4, verbose=True)
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "record=poll min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        (self.battery / "charge_now").unlink()
        _, stderr = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertIn("cannot read capacity", stderr)

    def test_invalid_current_limit_after_control_fails_safely(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4)
        process.stdout.readline()
        self.write(self.limit, "not-a-number\n")
        _, stderr = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode)
        self.assertIn("invalid current limit", stderr)
        self.assertEqual("100\n", self.limit.read_text())

    def test_unreadable_charge_input_after_control_restores_limit(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4)
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        (self.battery / "charge_full").unlink()
        (self.battery / "charge_full").mkdir()
        _, stderr = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode)
        self.assertEqual("100\n", self.limit.read_text())
        self.assertIn("cannot read capacity", stderr)

    def test_unwritable_current_limit_after_control_fails(self):
        self.write_charge(3414500, 6829000)
        process = self.start_daemon(polls=4, verbose=True)
        self.assertEqual(
            "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.assertEqual(
            "record=poll min=77 max=83 limit=84 target=84 capacity=50 "
            "state=charging\n",
            process.stdout.readline(),
        )
        self.limit.unlink()
        self.limit.mkdir()
        _, stderr = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode)
        self.assertIn("cannot read current limit", stderr)
        self.assertIn("cleanup write failed", stderr)

    def test_control_write_failure_is_fatal_and_cleanup_owns_restoration(self):
        self.limit.chmod(0o444)
        result = self.run_daemon()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("BCLM write failed", result.stderr)
        self.assertIn("cleanup write failed", result.stderr)
        self.assertEqual("80\n", self.limit.read_text())

    def test_int_and_term_exit_normally_and_restore_limit(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signum=signum):
                self.write(self.limit, "80\n")
                self.write_charge(3414500, 6829000)
                process = self.start_daemon(polls=10)
                self.assertEqual(
                    "record=startup min=77 max=83 limit=84 target=84 capacity=50 "
                    "state=charging\n",
                    process.stdout.readline(),
                )
                process.send_signal(signum)
                stdout, stderr = process.communicate(timeout=4)
                self.assertEqual(0, process.returncode, stderr)
                self.assertEqual("100\n", self.limit.read_text())
                self.assertIn("record=cleanup target=100 limit=100", stdout)


class SurfaceTests(unittest.TestCase):
    def test_openrc_and_package_surfaces_are_unchanged(self):
        root = SOURCE.parent
        makefile = (root / "Makefile").read_text()
        initd = (root / "t2saild.initd").read_text()
        confd = (root / "t2saild.confd").read_text()
        package = (root / "PKGBUILD").read_text()
        for mode in ("0700", "0755", "0644"):
            self.assertIn(mode, makefile)
        self.assertIn("OPENRC_CONFDIR", makefile)
        self.assertIn("t2saild_min=77", confd)
        self.assertIn("t2saild_max=83", confd)
        self.assertIn("t2saild_profile=performance", confd)
        self.assertIn("t2saild_batprofile=powersave", confd)
        self.assertIn('t2saild_args=""', confd)
        self.assertIn('t2saild_args="--verbose"', confd)
        self.assertIn("Capacity is the sensor", confd)
        self.assertIn("BCLM is the actuator", confd)
        self.assertIn("validated by readback", confd)
        self.assertEqual(
            'command_args="${t2saild_args} ${t2saild_max} ${t2saild_min} ${t2saild_profile} ${t2saild_batprofile}"',
            next(
                line
                for line in initd.splitlines()
                if line.startswith("command_args=")
            ),
        )
        self.assertIn("command=/usr/bin/t2saild", initd)
        self.assertLess(
            initd.index("${t2saild_max}"), initd.index("${t2saild_min}")
        )
        self.assertLess(
            initd.index("${t2saild_min}"), initd.index("${t2saild_profile}")
        )
        self.assertLess(
            initd.index("${t2saild_profile}"),
            initd.index("${t2saild_batprofile}"),
        )
        self.assertIn('respawn_delay="2"', initd)
        self.assertIn('respawn_max="5"', initd)
        self.assertIn('respawn_period="60"', initd)
        self.assertIn('supervise_daemon_args="--respawn-delay-step 2"', initd)
        self.assertIn('retry="SIGTERM/5"', initd)
        self.assertIn("depend() {", initd)
        self.assertIn("\tneed localmount", initd)
        self.assertIn("\tuse logger", initd)
        self.assertIn("need localmount", initd)
        self.assertIn("use logger", initd)
        self.assertIn(
            'output_logger="/usr/bin/logger -t t2saild -p daemon.info"', initd
        )
        self.assertIn(
            'error_logger="/usr/bin/logger -t t2saild -p daemon.err"', initd
        )
        self.assertIn("backup=('etc/conf.d/t2saild')", package)
        self.assertIn("'cpupower'", package)
        self.assertNotIn("python", package.lower())
        self.assertNotIn("systemd", package.lower())


if __name__ == "__main__":
    unittest.main()
