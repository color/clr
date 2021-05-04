# TODO(michael.cusack): Currently just completes the first arg (command name). Update to also support command args.
_clr_command_completion()
{
    # Completes the namespace:command.
    COMPREPLY=( $(clr completion1 "$cur") )
    # echo $COMPREPLY
    __ltrim_colon_completions "$cur"
}

_clr_completion()
{
    # Using "-o nospace" so we can allow the delegated `clr complete1` to decide
    # if the arguement is complete. This makes bash only split on newlines.
    local IFS=$'\n'

    local prev cur cword words
     _get_comp_words_by_ref -n : prev cur cword words

    # Complete clr command names if this is the first arg, or the first arg was
    # help and this is the second one.
    [ $cword -eq 1 ] && _clr_command_completion && return
    [ $cword -eq 2 ] && [[ ${words[1]} == "help" ]] && _clr_command_completion && return

    # Subsequent arguments. For now use default (file name) completion.
    _filedir

    return 0
}

complete -F _clr_completion -o nospace clr
