import requests
from lxml import html
TOKEN_URL:str = "https://www.mywellness.com/cloud/User/Login/"

def get_token(username:str, password: str)->str:
    header_info:dict = {
        "UserBinder.Username" : username,
        "UserBinder.Password": password,
        "UserBinder.IsFromLogin" : True,
        "UserBinder.KeepMeLogged" : False,

    }
    response: requests.Response = requests.post(TOKEN_URL, data=header_info)
    html_dom:dict = html.fromstring(response.text)

    
