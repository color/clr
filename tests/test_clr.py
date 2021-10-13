import pytest
import clr


def test_argtest(capsys):
    def check(args, expected):
        clr.main(["clr", "argtest"] + args)
        captured = capsys.readouterr()
        assert expected in captured.out

    def check_failure(args, expected_err, expected_exit_code):
        with pytest.raises(SystemExit) as e:
            clr.main(["clr", "argtest"] + args)
        captured = capsys.readouterr()
        assert expected_err in captured.err
        assert expected_exit_code == e.value.code

    check(["1", "2"], "a=1 b=2 c=4 d=None e=False f=True")
    check(["11", "2", "3"], "a=11 b=2 c=3 d=None e=False f=True")
    check(["1", "2", "3", "4"], "a=1 b=2 c=3 d=4 e=False f=True")
    check(["1", "2", "3", "4", "--e"], "a=1 b=2 c=3 d=4 e=True f=True")
    check(["1", "2", "--c=3"], "a=1 b=2 c=3 d=None e=False f=True")
    check(["1", "2", "--c", "3"], "a=1 b=2 c=3 d=None e=False f=True")
    check(["1", "2", "--c=3", "--d=4"], "a=1 b=2 c=3 d=4 e=False f=True")
    check(["1", "2", "--d=4", "--c=3"], "a=1 b=2 c=3 d=4 e=False f=True")
    check(["1", "2", "--d=3"], "a=1 b=2 c=4 d=3 e=False f=True")
    check(["1", "2", "--nof", "--e"], "a=1 b=2 c=4 d=None e=True f=False")
    check(["1", "2", "--nof", "--noe"], "a=1 b=2 c=4 d=None e=False f=False")
    check_failure(["1"], "one of the arguments --b b is required", 2)
    check_failure(
        ["11", "2", "--c=ccc"],
        "error: argument --c: invalid int value: 'ccc'",
        2
    )
    check(["1", "--b=2"], "a=1 b=2 c=4 d=None e=False f=True")
    check(["--a", "1", "--b=2"], "a=1 b=2 c=4 d=None e=False f=True")
    check(
        ["--a", "aaa", "--b", "bbb", "--c", "333", "--d", "ddd", "--e", "--nof"],
        "a=aaa b=bbb c=333 d=ddd e=True f=False",
    )


def test_argtest2(capsys):
    def check(args, expected):
        clr.main(["clr", "argtest2"] + args)
        captured = capsys.readouterr()
        assert expected in captured.out

    def check_failure(args, expected_err, expected_exit_code):
        with pytest.raises(SystemExit) as e:
            clr.main(["clr", "argtest2"] + args)
        captured = capsys.readouterr()
        assert expected_err in captured.err
        assert expected_exit_code == e.value.code

    check(["1", "2"], "a=1 b=2 c=() d=4 e=None f=False g=")
    check(["11", "2", "3"], "a=11 b=2 c=('3',) d=4 e=None f=False g=")
    check(["11", "2", "3", "4"], "a=11 b=2 c=('3', '4') d=4 e=None f=False g=")
    check(
        ["11", "2", "3", "4", "a", "b"],
        "a=11 b=2 c=('3', '4', 'a', 'b') d=4 e=None f=False g=",
    )
    check_failure(["11"], "the following arguments are required: b", 2)
    check(["11", "2", "3", "4", "--f"], "a=11 b=2 c=('3', '4') d=4 e=None f=True g=")
    check(
        ["11", "2", "3", "4", "--g=ggg", "--e=eee"],
        "a=11 b=2 c=('3', '4') d=4 e=eee f=False g=ggg",
    )
