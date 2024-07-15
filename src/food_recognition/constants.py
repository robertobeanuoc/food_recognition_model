import os 

SIMILAR_JINJA2_TEMPLATE: str = 'food_recognition/jinja2_templates/similar_files.jinja'
WAIT_TIME_OPEANAI_API: int =  int(os.getenv("WAIT_TIME_OPEANAI_API", 5))