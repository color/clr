_clr_command_completion()
{
    # Using "-o nospace" so we can allow the delegated `clr complete1` to decide
    # if the arguement is complete. This makes bash only split on newlines.
    local IFS=$'\n'
    # Completes the namespace:command.
    COMPREPLY=( $(clr completion1 "$cur") )
    __ltrim_colon_completions "$cur"
}

_clr_arg_completion()
{
    local IFS=$'\n'
    # Completes the flags.
    COMPREPLY=( $(clr completion2 ${words[1]} " $cur") )
}

_clr_completion()
{
    local prev cur cword words
     _get_comp_words_by_ref -n : prev cur cword words

    # Complete clr command names if this is the first arg, or the first arg was
    # help and this is the second one.
    if [ $cword -eq 1 ]
    then
        _clr_command_completion
        return
    fi
    if [ $cword -eq 2 ] && [[ ${words[1]} == "help" ]]
    then
        _clr_command_completion
        return
    fi

    # Previous arguement was a flag.
    if [[ $prev == --* ]]
    then

        # Check if it was a boolean flag.
        clr completion2 --bools_only ${words[1]} | grep "^$prev" > /dev/null
        if [ $? -eq 0 ]
        then
            # This will be an arg too.
            _clr_arg_completion
            return
        fi

        # This is a value, for now use default (file name) completion.
        _filedir
        return
    fi

    # This will be a flag.
    _clr_arg_completion

    return
}

complete -F _clr_completion -o nospace clr
