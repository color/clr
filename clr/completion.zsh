_clr () {
    raw_options=$(clr smart_complete "${words[@]}")
    if [ $? -eq 2 ]
    then
        _files
        return
    fi
    options_array=(${(@f)raw_options})
    for s ("$options_array[@]")
    do
        if [[ $s =~ " $" ]]
        then
            # Ends with a space to indicate a complete arg.
            compadd -U -- "${s: :-1}"
        else
            # Partial arg, don't append a space.
            compadd -U -S '' -- "${s}"
        fi
    done
}
compdef _clr clr
