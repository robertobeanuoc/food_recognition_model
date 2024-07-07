import logging 
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
app_logger:logging.Logger = logging.getLogger("food_classification")

