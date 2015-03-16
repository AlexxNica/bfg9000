ext2lang = {
    '.cpp': 'c++',
    '.c': 'c',
}

def lang(iterable):
    if any((i['lang'] == 'c++' for i in iterable)):
        return 'c++'
    else:
        return 'c'