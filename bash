function _naaman()
{
    local cur opts 
    if [ $COMP_CWORD -eq 1 ]; then
        cur=${COMP_WORDS[COMP_CWORD]}
        opts=$(echo "_COMPLETIONS_")
        COMPREPLY=( $(compgen -W "$opts" -- $cur) )
    fi
}

complete -F _naaman naaman
