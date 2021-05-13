_clr_complete()
{
    local IFS=$'\n'
    local prev cur cword words
    _get_comp_words_by_ref -n : prev cur cword words

    COMPREPLY=( $(clr smart_complete "${words[@]}") )

    if [ $? -eq 2 ]
    then
        _filedir
    else
        __ltrim_colon_completions "$cur"
    fi
}

complete -o nosort -o nospace -F _clr_complete clr
