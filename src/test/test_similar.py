import datetime
from food_recognition.similar_food import find_similar_food
from food_recognition.db import get_food_registers, get_glycemic_index
import sys


def test_get_food_types():
    find_similar_food(food_type="Fried Chicken")


def _dump_food_register_similarity_report(output_path: str) -> None:
    """Manual one-off report, not an automated test — hits the real DB/OpenAI
    and writes a CSV. Run directly: `python test_similar.py <output_file>`.
    Named with a leading underscore (and gated behind __main__ below) so
    pytest doesn't try to collect/run it as a test.
    """
    with open(output_path, "w") as f:
        f.write("file_uid, food, glycemic_index, similar, similar_glycemic_index, glycemic_index_difference\n")
        food_registers: dict = get_food_registers(start_date=datetime.date(2024, 7, 4))
        
        food_registers_filtered:dict  = food_registers
        #[food_register for food_register in food_registers if food_register['food_type'].lower() == 'banana']
        for food_register in food_registers_filtered:
            similar_food: str = find_similar_food(food_type=food_register['food_type'].lower())
            original_food: str = food_register['food_type']
            glycemic_index: int = food_register['glycemic_index']
            file_uid: str = food_register['file_uid']
            original_glycemic_index: int = get_glycemic_index(food_type=similar_food)
            glycemic_index_difference: int  =  None
            if original_glycemic_index:
                glycemic_index_difference: int = glycemic_index - original_glycemic_index

            output_string: str = f"{file_uid}, {original_food}, {glycemic_index}, {similar_food}, {original_glycemic_index}, {glycemic_index_difference}\n"
            f.write(output_string)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please provide the output file path")
        sys.exit(1)
    _dump_food_register_similarity_report(sys.argv[1])

