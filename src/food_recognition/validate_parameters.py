from uuid import UUID
import re 


class InvalidUUIDError(Exception):
    pass

def validate_uuid(uuid: str) -> None:
    try:
        UUID(uuid)
    except ValueError:
        raise InvalidUUIDError(uuid)
    
def validate_food_type(food_type: str) -> None:
    # food_type is embedded as a raw URL path segment (see food_register.js),
    # not a foreign key into glycemic_index — there's no DB relationship to
    # enforce here. This only guards against characters that would break URL
    # routing (e.g. '/') or path traversal; food names are otherwise free-form
    # (accents, digits, hyphens, apostrophes, etc. are all valid, e.g.
    # "whole-grain bread", "crème brûlée").
    if not food_type or not re.match(r"^[^/\\?#]+$", food_type):
        raise ValueError(f"Invalid food type: {food_type}")

