# TODO(michael.cusack): Currently just completes the first arg (command name). Update to also support command args.
_clr_completion()
{
    local IFS=$'\n'
    local cur prev opts

     _get_comp_words_by_ref -n : cur
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    COMPREPLY=( $(clr completion ${cur}) )

    __ltrim_colon_completions "$cur"
    return 0
}

complete -F _clr_completion -o nospace clr
