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



# if [[ ! "${COMPREPLY[@]}" == *: ]]; then
#   compopt +o nospace
# fi


complete -F _clr_completion -o nospace clr
