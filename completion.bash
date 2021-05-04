# TODO(michael.cusack): Currently just completes the first arg (command name). Update to also support command args.
_clr_completion()
{
    local IFS=$'\n'
    local cur cword
     _get_comp_words_by_ref -n : cur cword

    case $cword in
        1)
            # First argument. Completes the namespace:command.
            COMPREPLY=( $(clr completion1 "$cur") )
            # echo $COMPREPLY
            __ltrim_colon_completions "$cur"
            ;;
        *)
            # Subsequent arguments. For now use default (file name) completion.
            COMPREPLY=( $(compgen -o default -- "$cur") )
            ;;
    esac

    return 0
}

complete -F _clr_completion -o nospace clr
