if ! declare -F _get_comp_words_by_ref > /dev/null; then
    # Bash helper functions not avaliable.
    # `brew install bash-completion` on OSX.
    # Also make sure to source the bash_completion.sh in your .bash_profile.
    echo "Not installing clr completions. Please install/source bash-completion." 1>&2;
    return
fi

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

clr_complete_options="-o nospace"
# nosort is only avaliable in bash4+. os x still uses bash3 by default.
[[ ${BASH_VERSINFO[0]} -ge 4 ]] && \
    clr_complete_options="$clr_complete_options -o nosort"
complete  $clr_complete_options -F _clr_complete clr

