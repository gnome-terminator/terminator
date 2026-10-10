# tests/e2e is the GUI end-to-end suite, run only via tests/e2e/run_e2e.sh.
# Keep the unit lane (tests/run_tests.sh, pytest --doctest-modules over the
# whole tree) from importing/collecting anything here.  roundtrip_driver.py
# is still used by tests/test_m21_restore_roundtrip.py, as a subprocess.
collect_ignore_glob = ['*.py']
