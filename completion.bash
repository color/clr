# TODO(michael.cusack): Currently just completes the first arg (command name). Update to also support command args.
_clr_completion()
{
    local IFS=$'\n'

    case $COMP_CWORD in
        1)
            # First argument. Completes the namespace:command.
            _get_comp_words_by_ref -n : cur
            COMPREPLY=( $(clr completion1 "${COMP_WORDS[COMP_CWORD]}") )
            __ltrim_colon_completions "$cur"
            ;;
        *)
            # Subsequent arguments. For now use default (file name) completion.
            COMPREPLY=( $(compgen -o default -- "${COMP_WORDS[COMP_CWORD]}") )
            ;;
    esac

    return 0
}

complete -F _clr_completion -o nospace clr
