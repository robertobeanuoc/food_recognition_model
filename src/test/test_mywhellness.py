import os
from food_recognition.mywhelness import MyWellness
import datetime

username: str= os.getenv("MYWELLNESS_USERNAME")
password: str= os.getenv("MYWELLNESS_PASSWORD") 


my_wellness: MyWellness = MyWellness()


token, app_id = my_wellness.get_token_and_app_id(username=username, password=password)

start_date: datetime.date = datetime.date(2024, 8, 1)
end_date: datetime.date = datetime.date(2024, 8, 30)


movements_content: str = my_wellness._get_trainnings(token=token, app_id=app_id, start_date=start_date, end_date=end_date)
with open("/Users/rbean/temp/trainings.html", "w") as file:
    file.write(movements_content)

training_urls: list[str]
training_id_crs: list[str]
training_dates: list[str]

training_urls, training_id_crs, training_dates = my_wellness.get_trainning_urls_and_id_cr(token=token, app_id=app_id, start_date=start_date, end_date=end_date)

print(training_urls)
i:int = 0
for trainging_url in training_urls:
    training: str = my_wellness.get_training(id_cr=training_id_crs[i], position=i+1, day_open_session=training_dates[i])
    file_name: str = f"/Users/rbean/temp/training_{i}.html"
    with open(file_name, "w") as file:
        file.write(training)
    i = i + 1
