"""Garde-fous communs à l'héritage et aux anciennes administrations."""
from rest_framework.exceptions import ValidationError


def assert_legacy_configuration_write_allowed():
    raise ValidationError(
        "Les paramètres de politique et d'analyse sont désormais versionnés. "
        "Préparez une adaptation dans le Centre de configuration, puis faites-la publier par un autre utilisateur habilité."
    )


def validate_locks(keys, overrides, *, group):
    if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
        raise ValidationError({"locked_keys": "Une liste de clés section.paramètre est requise."})
    if keys and not group:
        raise ValidationError({"locked_keys": "Seul le Groupe peut verrouiller des paramètres."})
    available = {f"{section}.{key}" for section, values in overrides.items() for key in values}
    if set(keys) - available:
        raise ValidationError({"locked_keys": "Chaque clé verrouillée doit être explicitement définie dans ce profil."})
    return sorted(set(keys))
