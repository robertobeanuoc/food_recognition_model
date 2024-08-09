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
    if not re.match(r'^[a-z|A-Z|\s]+$', food_type):
        raise ValueError(f"Invalid food type: {food_type}")

