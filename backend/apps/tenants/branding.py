"""Nuance interne dérivée de la principale, hors des quatre choix de la filiale."""


def secondary_from_primary(primary):
    return "#" + "".join(
        f"{(int(primary[index:index + 2], 16) * 82 + 50) // 100:02x}"
        for index in (1, 3, 5)
    )
