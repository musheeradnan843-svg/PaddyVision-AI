import pandas as pd

from api.model_loader import agricultural_model


FEATURES = [
    "YEAR",
    "Station",
    "LATITUDE",
    "LONGITUDE",
    "ALT",
    "Avg_Max_Temp",
    "Avg_Min_Temp",
    "Avg_Rainfall",
    "Avg_Relative_Humidity",
    "Avg_Windspeed",
    "Avg_Cloud_Coverage",
    "Avg_Bright_Sunshine"
]


def predict_agricultural_yield(data: dict):

    input_data = pd.DataFrame(
        [data],
        columns=FEATURES
    )

    prediction = agricultural_model.predict(
        input_data
    )[0]

    return float(prediction)