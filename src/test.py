# from datetime import datetime, timedelta, timezone
# past = datetime.now(timezone.utc) + timedelta(days=1)
# present = datetime.now(timezone.utc)
# print(past > present)
#
# print(datetime.fromtimestamp(1748701883, timezone.utc))
# import os
#
# from src.database.utils import add_product

# print(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static"))

# UPLOAD_DIR = "static/uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)

# [('category', 'Недвижимость'), ('product_name', 'Тест'), ('product_price', '150'), ('product_description', 'Просто'), ('product_image', UploadFile(filename='1000009217.jpg', size=1216291, headers=Headers({'content-disposition': 'form-data; name="product_image"; filename="1000009217.jpg"', 'content-type': 'image/jpeg'})))]
#
# def parse_form_data(form_data):
#     product_data = {}
#     for d in form_data:
#         product_data[d[0]] = d[1]
#     return product_data

session_token = 1
def test(session_token):
    if session_token:
        if 1 == session_token:
            print("Вообще смак")
        print("Ода")
    print("О нет")

test(session_token)