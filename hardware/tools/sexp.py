"""Lecture et écriture des fichiers KiCad (expressions parenthésées).

Un fichier KiCad est un arbre de listes. Ici une liste est une `list` Python,
une chaîne entre guillemets est un `Q`, tout le reste (mots-clés, nombres) est
une `str` ordinaire. Garder cette distinction permet de réécrire un fichier
sans changer les guillemets.
"""


class Q(str):
    """Chaîne écrite entre guillemets dans le fichier."""


def parse(text):
    """Lit un texte et rend l'arbre (une seule expression racine)."""
    stack = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif c == '"':
            j = i + 1
            out = []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                    out.append({"n": "\n", "t": "\t"}.get(text[j], text[j]))
                else:
                    out.append(text[j])
                j += 1
            stack[-1].append(Q("".join(out)))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            stack[-1].append(text[i:j])
            i = j
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("expression mal parenthésée")
    return stack[0][0]


def load(path):
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def num(x):
    """Écrit un nombre sans zéros inutiles, au micromètre près."""
    if isinstance(x, int):
        return str(x)
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _atom(a):
    if isinstance(a, Q):
        esc = a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{esc}"'
    if isinstance(a, (int, float)):
        return num(a)
    return a


def dump(node, depth=0):
    """Écrit un arbre, une liste imbriquée par ligne."""
    if not isinstance(node, list):
        return _atom(node)
    if not any(isinstance(c, list) for c in node):
        return "(" + " ".join(_atom(c) for c in node) + ")"
    pad = "\t" * (depth + 1)
    head = []
    k = 0
    while k < len(node) and not isinstance(node[k], list):
        head.append(_atom(node[k]))
        k += 1
    lines = ["(" + " ".join(head)]
    for c in node[k:]:
        lines.append(pad + dump(c, depth + 1))
    lines.append("\t" * depth + ")")
    return "\n".join(lines)


def save(path, node):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(node) + "\n")


def head(node):
    return node[0] if isinstance(node, list) and node else None


def find(node, tag):
    """Premier enfant direct dont le mot-clé est `tag`, ou None."""
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


def find_all(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]
