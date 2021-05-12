import pytest
import clr

def test_argtest(capsys):
    def check(args, expected):
        clr.main(['clr', 'argtest'] + args)
        captured = capsys.readouterr()
        assert expected in captured.out

    def check_failure(args, expected):
        with pytest.raises(SystemExit):
            clr.main(['clr', 'argtest'] + args)
        captured = capsys.readouterr()
        assert expected in captured.err

    check(['1', '2'], 'a=1 b=2 c=4 d=None e=False f=True')
    check(['11', '2', '3'], 'a=11 b=2 c=3 d=None e=False f=True')
    check(['1', '2', '3', '4'], 'a=1 b=2 c=3 d=4 e=False f=True')
    check(['1', '2', '3', '4', '--e'], 'a=1 b=2 c=3 d=4 e=True f=True')
    check(['1', '2', '--c=3'], 'a=1 b=2 c=3 d=None e=False f=True')
    check(['1', '2', '--c', '3'], 'a=1 b=2 c=3 d=None e=False f=True')
    check(['1', '2', '--c=3', '--d=4'], 'a=1 b=2 c=3 d=4 e=False f=True')
    check(['1', '2', '--d=4', '--c=3'], 'a=1 b=2 c=3 d=4 e=False f=True')
    check(['1', '2', '--d=3'], 'a=1 b=2 c=4 d=3 e=False f=True')
    check(['1', '2', '--nof', '--e'], 'a=1 b=2 c=4 d=None e=True f=False')
    check_failure(['1'], 'Not all non-default arguments were specified!')
    check_failure(['11', '2', '--c=ccc'], "error: option --c: invalid integer value: 'ccc'")

    # Ideally should work, but doesn't.
    check_failure(['1', '--b=2'], 'Not all non-default arguments were specified!')


def test_argtest2(capsys):
    def check(args, expected):
        clr.main(['clr', 'argtest2'] + args)
        captured = capsys.readouterr()
        assert captured.out == f'{expected}\n'

    def check_failure(args, expected):
        with pytest.raises(SystemExit):
            clr.main(['clr', 'argtest2'] + args)
        captured = capsys.readouterr()
        assert captured.err == f'{expected}\n'

    check(['1', '2'], 'a=1 b=2 c=()')
    check(['11', '2', '3'], "a=11 b=2 c=('3',)")
    check(['11', '2', '3', '4'], "a=11 b=2 c=('3', '4')")
    check(['11', '2', '3', '4', 'a', 'b'], "a=11 b=2 c=('3', '4', 'a', 'b')")
    check_failure(['11'], "Not all non-default arguments were specified!")
