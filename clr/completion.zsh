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
            compadd -U -- "${s: :-1}"
        else
            compadd -U -S '' -- "${s}"
        fi
    done
}
