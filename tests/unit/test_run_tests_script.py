from unittest.mock import patch

from scripts import run_tests


def test_run_system_tests_targets_existing_manual_script():
    with patch.object(run_tests.subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0

        result = run_tests.run_system_tests()

    assert result == 0
    assert mock_run.call_args is not None
    cmd = mock_run.call_args.args[0]
    assert cmd[1].endswith("tests/manual/test_system.py")


def test_coverage_command_ignores_manual_tests():
    with patch.object(run_tests.subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0
        with patch(
            "sys.argv",
            ["run_tests.py", "--coverage"],
        ):
            result = run_tests.main()

    assert result == 0
    assert mock_run.call_args is not None
    cmd = mock_run.call_args.args[0]
    assert "--ignore=tests/manual" in cmd
